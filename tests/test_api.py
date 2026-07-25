"""API-level tests for the schema-content and note-data endpoints, and for
persisting extracted JSON alongside a note during /api/ingest.

Uses FastAPI's TestClient with a temporary vault/schema dir per test so
these don't touch the real vault/ or schemas/ folders.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main_mod  # noqa: E402
import app.dspy_modules as dm  # noqa: E402
from app.vault import Vault  # noqa: E402
from app.schemas import SchemaStore  # noqa: E402

SCHEMA = b"""{
  "title": "District Analysis",
  "type": "object",
  "properties": {
    "district": {"type": "string", "title": "District"},
    "population": {"type": "integer"}
  },
  "required": ["district"]
}"""


def make_client(tmp_path):
    main_mod.vault = Vault(tmp_path / "vault")
    main_mod.schema_store = SchemaStore(tmp_path / "schemas")
    return TestClient(main_mod.app)


def test_get_schema_content(tmp_path):
    c = make_client(tmp_path)
    c.post("/api/schemas", files={"file": ("district.json", SCHEMA, "application/json")})

    r = c.get("/api/schemas/district")
    assert r.status_code == 200
    assert r.json()["properties"]["district"]["type"] == "string"


def test_get_schema_content_404(tmp_path):
    c = make_client(tmp_path)
    assert c.get("/api/schemas/does-not-exist").status_code == 404


def test_note_data_404_when_absent(tmp_path):
    c = make_client(tmp_path)
    c.post("/api/notes", json={"title": "Plain Note", "body": "hello"})
    assert c.get("/api/notes/Plain-Note/data").status_code == 404


def test_ingest_with_schema_returns_extraction_only_no_note_yet(tmp_path, monkeypatch):
    """With a schema selected, /api/ingest should stop at extraction — no
    Markdown, no save. Converting/saving is the separate /api/render step."""
    c = make_client(tmp_path)
    c.post("/api/schemas", files={"file": ("district.json", SCHEMA, "application/json")})

    monkeypatch.setattr(
        dm, "extract_structured",
        lambda source, text, schema, max_chunks=8, chunk_size=6000, on_progress=None: dm.Extraction(
            data={"district": "Mysuru", "population": 3001000}, errors=[], raw="{}"
        ),
    )

    r = c.post(
        "/api/ingest",
        files=[("files", ("memo.txt", b"District: Mysuru, population 3001000.", "text/plain"))],
        data={"format_spec": "", "schema_name": "district", "save": "true"},
    )
    result = r.json()["results"][0]
    assert "note" not in result
    assert "saved" not in result
    assert result["extraction"]["schema"] == "district"
    assert result["extraction"]["valid"] is True
    assert result["extraction"]["data"] == {"district": "Mysuru", "population": 3001000}

    # Nothing should have been written to the vault at this stage.
    assert list((tmp_path / "vault").glob("*.md")) == []
    assert list((tmp_path / "vault").glob("*.json")) == []


def test_render_converts_extraction_to_markdown_and_saves(tmp_path):
    c = make_client(tmp_path)
    c.post("/api/schemas", files={"file": ("district.json", SCHEMA, "application/json")})

    r = c.post("/api/render", json={
        "data": {"district": "Mysuru", "population": 3001000},
        "schema_name": "district",
        "source_filename": "memo.txt",
        "save": True,
    })
    assert r.status_code == 200
    body = r.json()
    # No "title"/"name" field in the data, so the title falls back to the
    # source filename.
    assert body["title"] == "memo"
    assert "## District" in body["note"]
    assert "Mysuru" in body["note"]
    assert body["valid"] is True
    slug = body["saved"]
    assert slug

    data_res = c.get(f"/api/notes/{slug}/data")
    assert data_res.status_code == 200
    payload = data_res.json()
    assert payload["schema"] == "district"
    assert payload["data"]["district"] == "Mysuru"
    assert payload["valid"] is True

    # Deleting the note also removes the companion JSON.
    c.delete(f"/api/notes/{slug}")
    assert c.get(f"/api/notes/{slug}/data").status_code == 404


def test_render_without_save_does_not_persist(tmp_path):
    c = make_client(tmp_path)
    c.post("/api/schemas", files={"file": ("district.json", SCHEMA, "application/json")})

    r = c.post("/api/render", json={
        "data": {"district": "Mysuru"},
        "schema_name": "district",
        "source_filename": "memo.txt",
        "save": False,
    })
    body = r.json()
    assert body["saved"] is None
    assert list((tmp_path / "vault").glob("*.md")) == []
    assert list((tmp_path / "vault").glob("*.json")) == []


def test_render_reports_validation_errors_without_blocking(tmp_path):
    c = make_client(tmp_path)
    c.post("/api/schemas", files={"file": ("district.json", SCHEMA, "application/json")})

    # Missing the required "district" field.
    r = c.post("/api/render", json={
        "data": {"population": 100},
        "schema_name": "district",
        "source_filename": "memo.txt",
        "save": False,
    })
    body = r.json()
    assert body["valid"] is False
    assert body["errors"]
    # Still renders something useful even though it's invalid.
    assert "## Population" in body["note"]


def test_render_unknown_schema_404s(tmp_path):
    c = make_client(tmp_path)
    r = c.post("/api/render", json={
        "data": {"a": 1}, "schema_name": "does-not-exist", "save": False,
    })
    assert r.status_code == 404


ARRAY_SCHEMA = b"""{
  "title": "Strategy Points",
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "strategy_point_id": {"type": "string", "title": "Strategy Point ID"},
      "confidence": {"type": "string"}
    },
    "required": ["strategy_point_id"]
  }
}"""


def test_render_accepts_array_rooted_data(tmp_path):
    """A schema whose root type is "array" (e.g. a list of extracted
    records) must not be rejected as "not a JSON object" — this was a real
    bug: extraction hard-required a dict at the top level."""
    c = make_client(tmp_path)
    c.post("/api/schemas", files={"file": ("strategy.json", ARRAY_SCHEMA, "application/json")})

    data = [
        {"strategy_point_id": "STRATEGY_POINT_789", "confidence": "Verified"},
        {"strategy_point_id": "STRATEGY_POINT_101112", "confidence": "Verified"},
    ]
    r = c.post("/api/render", json={
        "data": data, "schema_name": "strategy", "source_filename": "memo.txt", "save": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert "## Item 1: STRATEGY_POINT_789" in body["note"]
    assert "## Item 2: STRATEGY_POINT_101112" in body["note"]
    # No "title"/"name" on a list root, so title falls back to the filename.
    assert body["title"] == "memo"

    slug = body["saved"]
    assert slug
    saved_data = c.get(f"/api/notes/{slug}/data").json()
    assert saved_data["data"] == data


def test_extract_structured_accepts_array_output(monkeypatch):
    """The DSPy-facing parse/validate path itself must accept an array,
    not just a dict, when the schema's root type is "array"."""
    schema = {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}}}}

    class FakeExtractor:
        def summarise(self, **kw):
            raise AssertionError("short text shouldn't need chunk summarisation")

        def extract(self, **kw):
            class Pred:
                data_json = '[{"id": "a"}, {"id": "b"}]'
            return Pred()

    monkeypatch.setattr(dm, "_ensure_modules", lambda: {"extract": FakeExtractor()})
    result = dm.extract_structured("doc.txt", "some text", schema)
    assert result.data == [{"id": "a"}, {"id": "b"}]
    assert result.errors == []


def _read_ndjson(response) -> list[dict]:
    import json as json_mod
    lines = [ln for ln in response.text.splitlines() if ln.strip()]
    return [json_mod.loads(ln) for ln in lines]


def test_ingest_stream_reports_progress_events(tmp_path, monkeypatch):
    c = make_client(tmp_path)

    def fake_compile(source, text, format_spec, max_chunks=8, chunk_size=6000, on_progress=None):
        if on_progress:
            on_progress({"step": "chunked", "total_chunks": 2})
            on_progress({"step": "summarizing", "index": 1, "total": 2})
            on_progress({"step": "summarizing", "index": 2, "total": 2})
            on_progress({"step": "composing"})
            on_progress({"step": "composed"})
        return dm.Compiled(title="Fake Title", note="Fake note body", tags=["x"])

    monkeypatch.setattr(dm, "compile_document", fake_compile)

    r = c.post(
        "/api/ingest/stream",
        files=[("files", ("memo.txt", b"Some content to compile.", "text/plain"))],
        data={"format_spec": "", "schema_name": "", "save": "false"},
    )
    assert r.status_code == 200
    events = _read_ndjson(r)

    kinds = [e["event"] for e in events]
    assert kinds[0] == "file_start"
    assert kinds[-2] == "file_done"
    assert kinds[-1] == "all_done"

    progress_steps = [e["step"] for e in events if e["event"] == "progress"]
    assert progress_steps == ["extracting_text", "extracted_text", "chunked",
                               "summarizing", "summarizing", "composing", "composed"]

    summarizing = [e for e in events if e.get("step") == "summarizing"]
    assert [e["index"] for e in summarizing] == [1, 2]

    done_event = next(e for e in events if e["event"] == "file_done")
    assert done_event["result"]["title"] == "Fake Title"


def test_ingest_stream_error_event_for_unsupported_file(tmp_path):
    c = make_client(tmp_path)
    r = c.post(
        "/api/ingest/stream",
        files=[("files", ("photo.png", b"\x89PNG", "image/png"))],
        data={"format_spec": "", "schema_name": "", "save": "false"},
    )
    events = _read_ndjson(r)
    # Only the initial "reading the file" step fires before it's rejected —
    # no chunking/summarizing/etc. for a file that never reaches the LLM.
    progress_steps = [e["step"] for e in events if e["event"] == "progress"]
    assert progress_steps == ["extracting_text"]
    done = next(e for e in events if e["event"] == "file_done")
    assert "error" in done["result"]
