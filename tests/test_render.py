"""Tests for the generic JSON -> Markdown renderer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.render import humanize, json_to_markdown  # noqa: E402


def test_humanize_snake_case():
    assert humanize("literacy_rate") == "Literacy Rate"


def test_humanize_camel_case():
    assert humanize("populationTotal") == "Population Total"


def test_humanize_acronym_preserved():
    assert humanize("GDP") == "GDP"


def test_flat_fields():
    md = json_to_markdown({"district": "Mysuru", "population": 3001000})
    assert "**District:** Mysuru" in md
    assert "**Population:** 3001000" in md


def test_schema_title_overrides_label():
    schema = {"properties": {"district": {"title": "District Name"}}}
    md = json_to_markdown({"district": "Mysuru"}, schema)
    assert "**District Name:** Mysuru" in md


def test_missing_value_marker():
    md = json_to_markdown({"literacy_rate": None})
    assert "_not found_" in md


def test_nested_object_becomes_heading():
    md = json_to_markdown({"demographics": {"population": 100}})
    assert "## Demographics" in md
    assert "**Population:** 100" in md


def test_list_of_scalars_becomes_bullets():
    md = json_to_markdown({"sectors": ["IT", "Agriculture", "Tourism"]})
    assert "- IT" in md
    assert "- Agriculture" in md


def test_list_of_objects_becomes_table():
    md = json_to_markdown({"taluks": [
        {"name": "Mysuru", "population": 900000},
        {"name": "Nanjangud", "population": 200000},
    ]})
    assert "| Name | Population |" in md
    assert "| Mysuru | 900000 |" in md
    assert "| Nanjangud | 200000 |" in md


def test_empty_list_marker():
    md = json_to_markdown({"sectors": []})
    assert "_none_" in md
