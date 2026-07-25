"""Render arbitrary schema-validated JSON into readable Markdown.

This is intentionally generic: it makes no assumptions about what fields a
schema defines. It only uses the schema, when present, to prettify field
labels (via each property's own "title"). This lets any user-supplied JSON
Schema render sensibly without us hard-coding field names.
"""
from __future__ import annotations

import re


def humanize(key: str) -> str:
    """camelCase / snake_case / kebab-case -> "Title Case", acronyms preserved."""
    if key.isupper():
        return key
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", key)
    spaced = spaced.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", spaced).strip().title()


def _label(key: str, props: dict) -> str:
    prop = (props or {}).get(key) or {}
    return prop.get("title") or humanize(key)


def _ordered_items(data: dict, schema: dict | None):
    """Yield (key, value) pairs in the schema's declared property order, so
    Markdown sections come out in a stable, predictable order that matches
    the schema rather than however the LLM happened to emit the JSON keys.
    Any keys present in `data` but not declared in the schema are appended
    at the end, in their original order, so nothing is silently dropped.
    """
    props = (schema or {}).get("properties", {})
    for key in props:
        if key in data:
            yield key, data[key]
    for key, value in data.items():
        if key not in props:
            yield key, value


def _table(rows: list[dict]) -> str:
    columns: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in columns:
                columns.append(key)
    header = "| " + " | ".join(humanize(c) for c in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body_rows = [
        "| " + " | ".join(str(row.get(c, "")) for c in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body_rows])


def json_to_markdown(data: dict, schema: dict | None = None, level: int = 2) -> str:
    """Render a dict (already validated against `schema`) as Markdown with one
    clearly defined section per field, ordered and labeled per the schema.

    Every field — scalar, nested object, or list — becomes its own heading,
    so the resulting document's structure visibly mirrors the schema rather
    than compressing simple fields into inline bold text. Nested objects
    recurse into deeper headings; lists of objects become tables; lists of
    scalars become bullets.
    """
    props = (schema or {}).get("properties", {})
    heading = "#" * min(level, 6)
    lines: list[str] = []

    for key, value in _ordered_items(data, schema):
        label = _label(key, props)
        sub_schema = props.get(key)
        lines.append(f"{heading} {label}")

        if isinstance(value, dict):
            lines.append(json_to_markdown(value, sub_schema, level + 1))
        elif isinstance(value, list):
            if not value:
                lines.append("_none_")
            elif all(isinstance(v, dict) for v in value):
                lines.append(_table(value))
            else:
                lines.extend(f"- {v}" for v in value)
        elif value is None or value == "":
            lines.append("_not found_")
        else:
            lines.append(str(value))
        lines.append("")

    return "\n".join(lines).strip() + "\n"
