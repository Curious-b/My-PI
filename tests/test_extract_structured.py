"""Tests for the deterministic parts of structured extraction: parsing raw
LLM output into JSON, and validating it against a JSON Schema. These don't
need DSPy or a running LLM — extract_structured() itself is exercised
manually against a real local model since it needs one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.dspy_modules import _parse_json_block, _schema_errors  # noqa: E402

SCHEMA = {
    "type": "object",
    "properties": {
        "district": {"type": "string"},
        "population": {"type": "integer"},
    },
    "required": ["district"],
}


def test_parse_raw_json():
    assert _parse_json_block('{"a": 1}') == {"a": 1}


def test_parse_fenced_json():
    text = '```json\n{"a": 1}\n```'
    assert _parse_json_block(text) == {"a": 1}


def test_parse_fenced_json_no_language_tag():
    text = '```\n{"a": 1}\n```'
    assert _parse_json_block(text) == {"a": 1}


def test_parse_json_with_surrounding_prose():
    text = 'Here is the JSON:\n{"a": 1}\nHope that helps!'
    assert _parse_json_block(text) == {"a": 1}


def test_schema_errors_valid():
    assert _schema_errors({"district": "Mysuru", "population": 100}, SCHEMA) == []


def test_schema_errors_missing_required():
    errors = _schema_errors({"population": 100}, SCHEMA)
    assert errors
    assert any("district" in e for e in errors)


def test_schema_errors_wrong_type():
    errors = _schema_errors({"district": "Mysuru", "population": "lots"}, SCHEMA)
    assert errors
    assert any("population" in e for e in errors)
