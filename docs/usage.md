# Usage

## Generate tests for a target module

```bash
ai-test-gen generate \
  --target targets/sample_ecommerce_app \
  --import-path targets.sample_ecommerce_app.order_service \
  --output-dir generated_tests
```

This scans every function in `--target`, sends each one's signature +
docstring + detected exceptions to the configured LLM, and writes one
`test_<module>_<function>_generated.py` file per function into
`--output-dir`.

## Run the generated suite

```bash
ai-test-gen run --tests-dir generated_tests
```

Prints a pass/fail/error/skip summary and exits non-zero if anything
failed (so it plugs directly into CI — see `.github/workflows/ci.yml`).

## View historical trend for a function

```bash
ai-test-gen trend --function targets.sample_ecommerce_app.order_service.place_order
```

Lists recent run outcomes for that function's generated tests, most
recent first — this is what makes "did this start failing after commit
X" answerable instead of just "is it failing right now."

## Before → After example

**Input** — the docstring and signature the scanner extracts from
`order_service.py`:

```python
def place_order(
    catalog: InMemoryCatalog,
    sku: str,
    quantity: int,
    discount_code: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Order:
    """
    Place an order for `quantity` units of `sku`...

    Raises:
        InsufficientStockError: if quantity > available stock, or quantity <= 0.
        InvalidDiscountError: if discount_code is provided but invalid/expired.
        KeyError: if sku does not exist in the catalog.
    """
```

**Output** — generated test cases (see the full file at
`generated_tests/test_order_service_place_order_generated.py`):

- `test_place_order_happy_path` — valid order decrements stock correctly
- `test_place_order_exact_remaining_stock` — **boundary**: ordering
  exactly the remaining quantity (catches off-by-one stock checks)
- `test_place_order_quantity_exceeds_stock_raises` — **error case**
  derived directly from the documented `InsufficientStockError`
- `test_place_order_zero_quantity_raises` / `..._negative_quantity_raises`
  — **edge cases** the docstring implies ("quantity <= 0") but that a
  human writing tests quickly often forgets
- `test_place_order_unknown_sku_raises_keyerror` — **error case** derived
  from the documented `KeyError`

Every generated function carries a `@pytest.mark.<category>` marker, which
is what lets `runner.py` and the storage layer break trend analysis down
by category (e.g. "are our error-case tests getting flakier over time?").
