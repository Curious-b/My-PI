"""Tests for the JSON Schema template store (no LLM involved)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas import InvalidSchema, SchemaStore  # noqa: E402

VALID_SCHEMA = b"""{
  "title": "District Analysis",
  "type": "object",
  "properties": {
    "district": {"type": "string", "title": "District"},
    "population": {"type": "integer"},
    "sectors": {"type": "array", "items": {"type": "string"}}
  },
  "required": ["district"]
}"""


def test_save_and_load(tmp_path):
    store = SchemaStore(tmp_path)
    summary = store.save("District Analysis.json", VALID_SCHEMA)
    assert summary["name"] == "District_Analysis"
    assert summary["title"] == "District Analysis"
    assert "district" in summary["fields"]

    loaded = store.load("District_Analysis")
    assert loaded["properties"]["district"]["type"] == "string"


def test_list(tmp_path):
    store = SchemaStore(tmp_path)
    store.save("a.json", VALID_SCHEMA)
    names = [s["name"] for s in store.list()]
    assert "a" in names


def test_delete(tmp_path):
    store = SchemaStore(tmp_path)
    store.save("a.json", VALID_SCHEMA)
    assert store.delete("a") is True
    assert store.delete("a") is False


def test_rejects_invalid_json(tmp_path):
    store = SchemaStore(tmp_path)
    try:
        store.save("bad.json", b"{not valid json")
        raised = False
    except InvalidSchema:
        raised = True
    assert raised


def test_rejects_non_object(tmp_path):
    store = SchemaStore(tmp_path)
    try:
        store.save("list.json", b"[1, 2, 3]")
        raised = False
    except InvalidSchema:
        raised = True
    assert raised


def test_rejects_invalid_json_schema(tmp_path):
    store = SchemaStore(tmp_path)
    # "type" must be a string or array of strings, not a number.
    try:
        store.save("bad-schema.json", b'{"type": 5}')
        raised = False
    except InvalidSchema:
        raised = True
    assert raised


def test_filename_sanitization(tmp_path):
    store = SchemaStore(tmp_path)
    store.save("../../etc/passwd.json", VALID_SCHEMA)
    # Should be sanitized to live inside the store root, not escape it.
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    assert files[0].parent == tmp_path
