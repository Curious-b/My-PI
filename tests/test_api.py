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


def test_ingest_with_schema_persists_companion_json(tmp_path, monkeypatch):
    c = make_client(tmp_path)
    c.post("/api/schemas", files={"file": ("district.json", SCHEMA, "application/json")})

    monkeypatch.setattr(
        dm, "extract_structured",
        lambda source, text, schema, max_chunks=8, on_progress=None: dm.Extraction(
            data={"district": "Mysuru", "population": 3001000}, errors=[], raw="{}"
        ),
    )

    r = c.post(
        "/api/ingest",
        files=[("files", ("memo.txt", b"District: Mysuru, population 3001000.", "text/plain"))],
        data={"format_spec": "", "schema_name": "district", "save": "true"},
    )
    result = r.json()["results"][0]
    slug = result["saved"]
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


def test_ingest_without_save_does_not_persist_data(tmp_path, monkeypatch):
    c = make_client(tmp_path)
    c.post("/api/schemas", files={"file": ("district.json", SCHEMA, "application/json")})
    monkeypatch.setattr(
        dm, "extract_structured",
        lambda source, text, schema, max_chunks=8, on_progress=None: dm.Extraction(
            data={"district": "Mysuru"}, errors=[], raw="{}"
        ),
    )
    r = c.post(
        "/api/ingest",
        files=[("files", ("memo.txt", b"District: Mysuru.", "text/plain"))],
        data={"format_spec": "", "schema_name": "district", "save": "false"},
    )
    result = r.json()["results"][0]
    assert result["saved"] is None
    # Nothing was saved, so there is no slug to have data under, and no
    # stray file should have been written anywhere in the temp vault.
    assert list((tmp_path / "vault").glob("*.json")) == []


def _read_ndjson(response) -> list[dict]:
    import json as json_mod
    lines = [ln for ln in response.text.splitlines() if ln.strip()]
    return [json_mod.loads(ln) for ln in lines]


def test_ingest_stream_reports_progress_events(tmp_path, monkeypatch):
    c = make_client(tmp_path)

    def fake_compile(source, text, format_spec, max_chunks=8, on_progress=None):
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
