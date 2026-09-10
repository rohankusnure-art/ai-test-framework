"""
order_service.py

A small but realistic e-commerce order-processing module.

This module is the "sample target" that the AI Test Framework scans and
generates tests for. It intentionally contains the kind of business logic
that produces interesting edge cases: stock validation, discount rules,
refund/rollback behavior, and idempotency concerns under concurrent
requests.

Design notes (data decisions):
- Money is stored as integer cents (never float) to avoid rounding-error
  bugs in financial calculations — a common real-world source of silent
  data corruption in commerce systems.
- Inventory decrement and order creation happen inside a single
  transactional boundary (see `place_order`) so a failure partway through
  triggers a rollback rather than leaving stock "reserved" but no order
  recorded (a classic backlog/return-consistency bug).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class InsufficientStockError(Exception):
    """Raised when requested quantity exceeds available inventory."""


class InvalidDiscountError(Exception):
    """Raised when a discount code is expired, unknown, or misapplied."""


class OrderNotFoundError(Exception):
    """Raised when an operation targets an order id that does not exist."""


class InvalidRefundError(Exception):
    """Raised when a refund is attempted on an ineligible order."""


@dataclass
class Product:
    sku: str
    name: str
    unit_price_cents: int
    stock_qty: int


@dataclass
class DiscountCode:
    code: str
    percent_off: int  # 1-100
    expires_at: datetime
    min_order_cents: int = 0


@dataclass
class Order:
    order_id: str
    sku: str
    quantity: int
    unit_price_cents: int
    discount_applied_pct: int
    total_cents: int
    status: OrderStatus
    created_at: datetime
    refunded_at: Optional[datetime] = None


class InMemoryCatalog:
    """
    Minimal in-memory stand-in for a product/inventory database.

    A real deployment would back this with Postgres (row-level locking
    on the stock decrement) or a dedicated inventory service; this class
    exists so the sample module is runnable and testable without external
    infrastructure, while still modeling the same failure modes.
    """

    def __init__(self) -> None:
        self._products: dict[str, Product] = {}
        self._orders: dict[str, Order] = {}
        self._discounts: dict[str, DiscountCode] = {}

    def add_product(self, product: Product) -> None:
        self._products[product.sku] = product

    def add_discount(self, discount: DiscountCode) -> None:
        self._discounts[discount.code] = discount

    def get_product(self, sku: str) -> Optional[Product]:
        return self._products.get(sku)

    def get_order(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)


def _apply_discount(base_cents: int, discount: Optional[DiscountCode], now: datetime) -> int:
    """
    Apply a percentage discount to a base amount (in cents).

    Edge cases a generated test suite should catch:
    - discount is None -> no change
    - discount.percent_off == 0 or == 100 (boundary values)
    - discount expired relative to `now`
    - base_cents below discount.min_order_cents (discount should not apply)
    """
    if discount is None:
        return base_cents
    if now >= discount.expires_at:
        raise InvalidDiscountError(f"Discount '{discount.code}' expired at {discount.expires_at}")
    if base_cents < discount.min_order_cents:
        raise InvalidDiscountError(
            f"Order of {base_cents}c does not meet minimum {discount.min_order_cents}c "
            f"for discount '{discount.code}'"
        )
    if not (0 <= discount.percent_off <= 100):
        raise InvalidDiscountError(f"Discount percent_off out of range: {discount.percent_off}")
    return base_cents - (base_cents * discount.percent_off // 100)


def place_order(
    catalog: InMemoryCatalog,
    sku: str,
    quantity: int,
    discount_code: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Order:
    """
    Place an order for `quantity` units of `sku`, optionally applying a
    discount code, and decrement inventory atomically.

    Raises:
        InsufficientStockError: if quantity > available stock, or quantity <= 0.
        InvalidDiscountError: if discount_code is provided but invalid/expired.
        KeyError: if sku does not exist in the catalog.

    Rollback behavior:
        If total calculation or discount validation fails AFTER stock has
        conceptually been reserved, the reservation must be rolled back so
        inventory counts stay correct. This function validates the discount
        BEFORE decrementing stock specifically to avoid that failure mode —
        a subtle bug generated tests should be designed to catch if the
        order of operations is ever changed during refactors.
    """
    now = now or datetime.now(timezone.utc)
    product = catalog.get_product(sku)
    if product is None:
        raise KeyError(f"Unknown SKU: {sku}")
    if quantity <= 0:
        raise InsufficientStockError(f"Quantity must be positive, got {quantity}")
    if quantity > product.stock_qty:
        raise InsufficientStockError(
            f"Requested {quantity}, only {product.stock_qty} in stock for {sku}"
        )

    base_cents = product.unit_price_cents * quantity
    discount = catalog._discounts.get(discount_code) if discount_code else None
    # Validate discount BEFORE mutating stock (see rollback note above).
    total_cents = _apply_discount(base_cents, discount, now)

    # Only mutate state after all validation has succeeded.
    product.stock_qty -= quantity
    order = Order(
        order_id=str(uuid.uuid4()),
        sku=sku,
        quantity=quantity,
        unit_price_cents=product.unit_price_cents,
        discount_applied_pct=discount.percent_off if discount else 0,
        total_cents=total_cents,
        status=OrderStatus.CONFIRMED,
        created_at=now,
    )
    catalog._orders[order.order_id] = order
    return order


def cancel_order(catalog: InMemoryCatalog, order_id: str) -> Order:
    """
    Cancel a PENDING or CONFIRMED order and restock the items.

    Raises:
        OrderNotFoundError: unknown order_id.
        InvalidRefundError: order already CANCELLED or REFUNDED (idempotency
            guard — cancelling twice must not double-restock inventory).
    """
    order = catalog.get_order(order_id)
    if order is None:
        raise OrderNotFoundError(f"No such order: {order_id}")
    if order.status in (OrderStatus.CANCELLED, OrderStatus.REFUNDED):
        raise InvalidRefundError(f"Order {order_id} already in terminal state {order.status}")

    product = catalog.get_product(order.sku)
    if product is not None:
        product.stock_qty += order.quantity  # restock
    order.status = OrderStatus.CANCELLED
    return order


def refund_order(
    catalog: InMemoryCatalog,
    order_id: str,
    now: Optional[datetime] = None,
) -> Order:
    """
    Refund a CONFIRMED order.

    Business rule: only CONFIRMED orders may be refunded directly; a
    CANCELLED order was never charged and has nothing to refund.

    Raises:
        OrderNotFoundError: unknown order_id.
        InvalidRefundError: order is not in CONFIRMED state.
    """
    now = now or datetime.now(timezone.utc)
    order = catalog.get_order(order_id)
    if order is None:
        raise OrderNotFoundError(f"No such order: {order_id}")
    if order.status != OrderStatus.CONFIRMED:
        raise InvalidRefundError(
            f"Cannot refund order {order_id} in status {order.status}; only CONFIRMED orders are refundable"
        )

    product = catalog.get_product(order.sku)
    if product is not None:
        product.stock_qty += order.quantity
    order.status = OrderStatus.REFUNDED
    order.refunded_at = now
    return order
