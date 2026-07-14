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
    """Recursively render a dict (already validated against `schema`) as Markdown."""
    props = (schema or {}).get("properties", {})
    heading = "#" * min(level, 6)
    lines: list[str] = []

    for key, value in data.items():
        label = _label(key, props)
        sub_schema = props.get(key)

        if isinstance(value, dict):
            lines.append(f"{heading} {label}")
            lines.append(json_to_markdown(value, sub_schema, level + 1))
        elif isinstance(value, list):
            if not value:
                lines.append(f"**{label}:** _none_")
            elif all(isinstance(v, dict) for v in value):
                lines.append(f"{heading} {label}")
                lines.append(_table(value))
            else:
                lines.append(f"{heading} {label}")
                lines.extend(f"- {v}" for v in value)
        elif value is None or value == "":
            lines.append(f"**{label}:** _not found_")
        else:
            lines.append(f"**{label}:** {value}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"
