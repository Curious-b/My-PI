"""Tests for the generic JSON -> Markdown renderer.

Every field becomes its own heading section (labeled and ordered per the
schema), rather than being compressed into inline bold text — so the
document's structure visibly mirrors the schema.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.render import humanize, json_to_markdown, render_document  # noqa: E402


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


# --- render_document(): array-rooted schemas ------------------------------
STRATEGY_POINT_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "strategy_point_id": {"type": "string", "title": "Strategy Point ID"},
            "delivery_mechanism_or_target": {"type": "array", "items": {"type": "string"}},
            "named_leaders": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "named_leader_id": {"type": "string"},
                        "name": {"type": "string"},
                    },
                },
            },
            "confidence": {"type": "string"},
        },
    },
}

STRATEGY_POINTS = [
    {
        "strategy_point_id": "STRATEGY_POINT_789",
        "delivery_mechanism_or_target": ["Chandrakant Kothiwale", "Uttam Patil"],
        "named_leaders": [
            {"named_leader_id": "LEADER_123", "name": "Chandrakant Kothiwale"},
            {"named_leader_id": "LEADER_456", "name": "Uttam Patil"},
        ],
        "confidence": "Verified",
    },
    {
        "strategy_point_id": "STRATEGY_POINT_101112",
        "delivery_mechanism_or_target": ["Chandrakant Kothiwale"],
        "named_leaders": [{"named_leader_id": "LEADER_789", "name": "Chandrakant Kothiwale"}],
        "confidence": "Verified",
    },
]


def test_render_document_dispatches_dict_to_json_to_markdown():
    schema = {"properties": {"district": {}}}
    assert render_document({"district": "Mysuru"}, schema) == json_to_markdown({"district": "Mysuru"}, schema)


def test_render_document_array_root_one_section_per_item():
    md = render_document(STRATEGY_POINTS, STRATEGY_POINT_SCHEMA)
    assert "## Item 1: STRATEGY_POINT_789" in md
    assert "## Item 2: STRATEGY_POINT_101112" in md
    # Item label comes from the first schema-declared property.
    assert md.index("## Item 1:") < md.index("## Item 2:")


def test_render_document_array_item_nested_fields_render():
    md = render_document(STRATEGY_POINTS, STRATEGY_POINT_SCHEMA)
    # Nested list-of-scalars ("delivery_mechanism_or_target") -> bullets.
    assert "- Chandrakant Kothiwale" in md
    assert "- Uttam Patil" in md
    # Nested list-of-dicts ("named_leaders") -> table with humanized columns.
    assert "| Named Leader Id | Name |" in md
    assert "| LEADER_123 | Chandrakant Kothiwale |" in md


def test_render_document_empty_array():
    assert render_document([], STRATEGY_POINT_SCHEMA) == "_none_\n"


def test_render_document_array_item_without_matching_schema_property_falls_back():
    # No "title"/"name"/"id" and the item schema's first property isn't
    # present in the item -> falls back to a plain index label.
    md = render_document([{"other": "value"}], {"type": "array", "items": {"properties": {"missing": {}}}})
    assert "## Item 1: Item 1" in md
