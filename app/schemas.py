"""Storage for user-supplied JSON Schema template files.

Users bring their own schema per document type (e.g. "district-analysis.json")
and upload it through the UI. This module only stores and validates those
files — it never invents or guesses schema content. Schemas live in a local
folder, same privacy model as the vault.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema


class InvalidSchema(Exception):
    """Raised when an uploaded file isn't valid JSON, or isn't a valid JSON Schema."""


def _sanitize_name(filename: str) -> str:
    stem = Path(filename).stem
    safe = re.sub(r"[^\w\-]", "_", stem)
    return safe or "schema"


class SchemaStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.root / f"{_sanitize_name(name)}.json"

    def save(self, filename: str, data: bytes) -> dict:
        try:
            schema = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise InvalidSchema(f"'{filename}' is not valid JSON: {exc}") from exc

        if not isinstance(schema, dict):
            raise InvalidSchema(f"'{filename}' must be a JSON object (a JSON Schema), got {type(schema).__name__}")

        validator_cls = jsonschema.validators.validator_for(schema, default=jsonschema.Draft7Validator)
        try:
            validator_cls.check_schema(schema)
        except jsonschema.exceptions.SchemaError as exc:
            raise InvalidSchema(f"'{filename}' is not a valid JSON Schema: {exc.message}") from exc

        path = self._path(filename)
        path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        return self._summary(path.stem, schema)

    @staticmethod
    def _summary(name: str, schema: dict) -> dict:
        return {
            "name": name,
            "title": schema.get("title") or name,
            "description": schema.get("description", ""),
            "fields": list(schema.get("properties", {}).keys()),
        }

    def list(self) -> list[dict]:
        out = []
        for path in sorted(self.root.glob("*.json")):
            try:
                out.append(self._summary(path.stem, json.loads(path.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
        return out

    def load(self, name: str) -> dict:
        path = self._path(name)
        if not path.exists():
            raise FileNotFoundError(name)
        return json.loads(path.read_text(encoding="utf-8"))

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if path.exists():
            path.unlink()
            return True
        return False
