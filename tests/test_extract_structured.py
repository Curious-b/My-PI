"""Tests for the deterministic parts of structured extraction: parsing raw
LLM output into JSON. These don't need DSPy or a running LLM —
extract_structured() itself is exercised manually against a real local
model since it needs one. Schema validation tests live in test_schemas.py,
next to validate_instance()'s home in app/schemas.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.dspy_modules import _parse_json_block  # noqa: E402


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
