"""Tests for the generic JSON -> Markdown renderer.

Every field becomes its own heading section (labeled and ordered per the
schema), rather than being compressed into inline bold text — so the
document's structure visibly mirrors the schema.
"""
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


def test_flat_fields_become_sections():
    md = json_to_markdown({"district": "Mysuru", "population": 3001000})
    assert "## District" in md
    assert "Mysuru" in md
    assert "## Population" in md
    assert "3001000" in md


def test_schema_title_overrides_label():
    schema = {"properties": {"district": {"title": "District Name"}}}
    md = json_to_markdown({"district": "Mysuru"}, schema)
    assert "## District Name" in md
    assert "Mysuru" in md


def test_missing_value_marker():
    md = json_to_markdown({"literacy_rate": None})
    assert "## Literacy Rate" in md
    assert "_not found_" in md


def test_nested_object_becomes_deeper_heading():
    md = json_to_markdown({"demographics": {"population": 100}})
    assert "## Demographics" in md
    assert "### Population" in md
    assert "100" in md


def test_list_of_scalars_becomes_bullets():
    md = json_to_markdown({"sectors": ["IT", "Agriculture", "Tourism"]})
    assert "## Sectors" in md
    assert "- IT" in md
    assert "- Agriculture" in md


def test_list_of_objects_becomes_table():
    md = json_to_markdown({"taluks": [
        {"name": "Mysuru", "population": 900000},
        {"name": "Nanjangud", "population": 200000},
    ]})
    assert "## Taluks" in md
    assert "| Name | Population |" in md
    assert "| Mysuru | 900000 |" in md
    assert "| Nanjangud | 200000 |" in md


def test_empty_list_marker():
    md = json_to_markdown({"sectors": []})
    assert "## Sectors" in md
    assert "_none_" in md


def test_field_order_follows_schema_not_dict_order():
    # The extracted JSON's key order (population before district) should NOT
    # dictate section order — the schema's declared property order should.
    schema = {"properties": {"district": {}, "population": {}}}
    data = {"population": 100, "district": "Mysuru"}
    md = json_to_markdown(data, schema)
    assert md.index("## District") < md.index("## Population")


def test_unschemad_extra_keys_still_render_at_the_end():
    schema = {"properties": {"district": {}}}
    data = {"district": "Mysuru", "extra_note": "not in schema"}
    md = json_to_markdown(data, schema)
    assert "## District" in md
    assert "## Extra Note" in md
    assert md.index("## District") < md.index("## Extra Note")
