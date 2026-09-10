"""Unit tests for ai_test_framework.generator.*"""

import json

import pytest

from ai_test_framework.config import Config
from ai_test_framework.generator.llm_client import (
    LLMClientError,
    NullLLMClient,
    _parse_json_array,
    get_llm_client,
)
from ai_test_framework.generator.prompt_templates import build_user_prompt
from ai_test_framework.generator.test_writer import write_test_file
from ai_test_framework.scanner.repo_scanner import FunctionInfo, ParamInfo


def test_parse_json_array_strips_markdown_fences():
    raw = '```json\n[{"name": "test_x"}]\n```'
    parsed = _parse_json_array(raw)
    assert parsed == [{"name": "test_x"}]


def test_parse_json_array_rejects_non_array():
    with pytest.raises(LLMClientError):
        _parse_json_array('{"not": "an array"}')


def test_parse_json_array_rejects_invalid_json():
    with pytest.raises(LLMClientError):
        _parse_json_array("not json at all")


def test_get_llm_client_falls_back_to_null_client_without_api_key():
    config = Config(llm_provider="openai", openai_api_key="")
    client = get_llm_client(config)
    assert isinstance(client, NullLLMClient)


def test_null_llm_client_returns_valid_spec_shape():
    client = NullLLMClient()
    specs = client.generate_test_specs("system", "user")
    assert len(specs) == 1
    assert specs[0]["name"].startswith("test_")
    assert specs[0]["category"] == "happy_path"


def test_build_user_prompt_includes_function_details():
    func = FunctionInfo(
        name="place_order",
        qualified_name="place_order",
        module_path="order_service.py",
        params=[ParamInfo(name="sku", annotation="str")],
        return_annotation="Order",
        docstring="Places an order.",
        raises=["InsufficientStockError"],
    )
    prompt = build_user_prompt(func, max_cases=4)
    assert "place_order" in prompt
    assert "InsufficientStockError" in prompt
    assert "Places an order." in prompt


def test_write_test_file_generates_valid_python(tmp_path):
    func = FunctionInfo(
        name="add",
        qualified_name="add",
        module_path="sample.py",
        params=[ParamInfo(name="a"), ParamInfo(name="b")],
    )
    specs = [
        {
            "name": "test_add_happy_path",
            "description": "adds two positive numbers",
            "category": "happy_path",
            "inputs": {"a": 1, "b": 2},
            "expected": {"returns": 3},
        },
        {
            "name": "test_add_negative_raises",
            "description": "negative input raises",
            "category": "error_case",
            "inputs": {"a": -1, "b": 0},
            "expected": {"raises": "ValueError"},
        },
    ]
    output_path = write_test_file(func, specs, tmp_path, import_path="sample")
    content = output_path.read_text()

    assert "def test_add_happy_path" in content
    assert "def test_add_negative_raises" in content
    assert "pytest.raises(ValueError)" in content
    compile(content, str(output_path), "exec")  # must be syntactically valid Python
