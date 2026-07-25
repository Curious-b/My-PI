"""FastAPI application — the private LLM Wiki server.

Bound to 127.0.0.1 by default (see config), so it is never exposed to the
network. Serves a single-page frontend plus a small JSON API.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import ingest as ingest_mod
from . import render as render_mod
from .config import settings
from .graph import build_graph
from .llm import llm_status
from .models import GenerateIn, NoteIn, QueryIn
from .retrieval import get_retriever
from .schemas import InvalidSchema, SchemaStore
from .vault import Vault, slugify

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="My-PI — Private LLM Wiki", version="0.1.0")

vault = Vault(settings.vault_dir)
schema_store = SchemaStore(settings.schema_dir)


def retriever():
    # Rebuilt each call so newly-saved notes are always searchable. The
    # keyword fallback is cheap; the vector store caches its own index.
    return get_retriever(vault)


# --------------------------------------------------------------------------
# Notes CRUD
# --------------------------------------------------------------------------
@app.get("/api/notes")
def list_notes():
    return [n.to_summary() for n in vault.all()]


@app.get("/api/notes/{slug}")
def get_note(slug: str):
    note = vault.get(slug)
    if note is None:
        raise HTTPException(404, f"Note '{slug}' not found")
    return note.to_dict()


@app.post("/api/notes")
def create_note(payload: NoteIn):
    note = vault.save(payload.title, payload.body, payload.tags, payload.slug)
    return note.to_dict()


@app.put("/api/notes/{slug}")
def update_note(slug: str, payload: NoteIn):
    note = vault.save(payload.title, payload.body, payload.tags, slug=slug)
    return note.to_dict()


@app.delete("/api/notes/{slug}")
def delete_note(slug: str):
    if not vault.delete(slug):
        raise HTTPException(404, f"Note '{slug}' not found")
    return {"deleted": slug}


@app.get("/api/notes/{slug}/data")
def get_note_data(slug: str):
    """The structured JSON that was extracted for this note, if it was
    created via schema-based extraction (see /api/ingest)."""
    payload = vault.get_data(slug)
    if payload is None:
        raise HTTPException(404, f"No extracted JSON for '{slug}'")
    return payload


# --------------------------------------------------------------------------
# Graph
# --------------------------------------------------------------------------
@app.get("/api/graph")
def graph(tags: bool = True):
    return build_graph(vault, include_tags=tags)


# --------------------------------------------------------------------------
# Search (no LLM required)
# --------------------------------------------------------------------------
@app.get("/api/search")
def search(q: str, k: int = 8):
    hits = retriever().search(q, k=k)
    return [{"slug": h.slug, "title": h.title, "snippet": h.snippet,
             "score": round(h.score, 3)} for h in hits]


# --------------------------------------------------------------------------
# LLM-powered: query (RAG) & generate (custom format)
# --------------------------------------------------------------------------
@app.get("/api/status")
def status():
    return {
        "vault_dir": str(settings.vault_dir),
        "note_count": len(list(vault.root.glob("*.md"))),
        "retriever": type(retriever()).__name__,
        "llm": llm_status(),
    }


@app.post("/api/query")
def query(payload: QueryIn):
    hits = retriever().search(payload.question, k=payload.k)
    try:
        from . import dspy_modules

        result = dspy_modules.ask(payload.question, hits)
        return {
            "answer": result.answer,
            "reasoning": result.reasoning,
            "sources": result.sources,
            "llm": True,
        }
    except Exception as exc:
        # LLM unavailable: still return the retrieved notes so the KB is useful.
        return JSONResponse(
            status_code=200,
            content={
                "answer": None,
                "error": str(exc),
                "sources": [{"slug": h.slug, "title": h.title,
                             "snippet": h.snippet, "score": round(h.score, 3)}
                            for h in hits],
                "llm": False,
            },
        )


@app.post("/api/generate")
def generate(payload: GenerateIn):
    hits = retriever().search(payload.topic, k=payload.k) if payload.k else []
    try:
        from . import dspy_modules

        draft = dspy_modules.draft_note(payload.topic, payload.format_spec, hits)
    except Exception as exc:
        raise HTTPException(
            503,
            detail=(
                f"Note generation needs the local LLM. {exc}"
            ),
        )

    saved = None
    if payload.save:
        note = vault.save(payload.topic, draft.note, draft.tags)
        saved = note.slug

    return {
        "title": payload.topic,
        "slug": slugify(payload.topic),
        "note": draft.note,
        "tags": draft.tags,
        "saved": saved,
    }


# --------------------------------------------------------------------------
# JSON Schema library (bring-your-own schema per document type)
# --------------------------------------------------------------------------
@app.get("/api/schemas")
def list_schemas():
    return schema_store.list()


@app.post("/api/schemas")
async def upload_schema(file: UploadFile = File(...)):
    data = await file.read()
    try:
        return schema_store.save(file.filename or "schema", data)
    except InvalidSchema as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/schemas/{name}")
def get_schema(name: str):
    try:
        return schema_store.load(name)
    except FileNotFoundError:
        raise HTTPException(404, f"Schema '{name}' not found")


@app.delete("/api/schemas/{name}")
def delete_schema(name: str):
    if not schema_store.delete(name):
        raise HTTPException(404, f"Schema '{name}' not found")
    return {"deleted": name}


# --------------------------------------------------------------------------
# Upload documents (PDF/Word/Excel/CSV/text) -> compiled Markdown notes
# --------------------------------------------------------------------------
def _process_file(
    name: str, data: bytes, *, schema: dict | None, schema_name: str,
    format_spec: str, save: bool, on_progress: Callable[[dict], None] | None = None,
) -> dict:
    """Extract + compile (or schema-extract) one document into a note.

    Shared by the plain /api/ingest endpoint and the streaming
    /api/ingest/stream endpoint. `on_progress`, if given, is forwarded into
    the DSPy layer and also called for the extraction/save steps here, so a
    caller can report live progress through a slow local-model run.
    """
    def emit(step: str, **info):
        if on_progress:
            on_progress({"step": step, **info})

    # 1) Extract text from the document.
    emit("extracting_text")
    try:
        extracted = ingest_mod.extract(name, data)
    except (ingest_mod.UnsupportedFile, ingest_mod.MissingParser) as exc:
        return {"filename": name, "error": str(exc)}

    if not extracted.text.strip():
        return {
            "filename": name,
            "error": "No extractable text found (is it a scanned/image-only PDF?).",
        }
    emit("extracted_text", kind=extracted.kind, chars=len(extracted.text))

    # 2) Turn it into a note via DSPy (LLM): either free-form (format_spec)
    #    or, if a schema was chosen, strict JSON-schema extraction rendered
    #    to Markdown. Fall back to raw extracted text if the LLM is offline.
    extraction_info = None
    try:
        from . import dspy_modules

        if schema is not None:
            extraction = dspy_modules.extract_structured(
                name, extracted.text, schema, max_chunks=settings.max_chunks,
                chunk_size=settings.chunk_size, on_progress=on_progress)
            title_val = extraction.data.get("title") or extraction.data.get("name")
            title = str(title_val).strip() if title_val else Path(name).stem.replace("-", " ").replace("_", " ")
            note_md = render_mod.json_to_markdown(extraction.data, schema)
            raw_tags = extraction.data.get("tags")
            tags = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else []
            used_llm = True
            extraction_info = {
                "schema": schema_name,
                "valid": not extraction.errors,
                "errors": extraction.errors,
                "data": extraction.data,
            }
        else:
            compiled = dspy_modules.compile_document(
                name, extracted.text, format_spec, max_chunks=settings.max_chunks,
                chunk_size=settings.chunk_size, on_progress=on_progress)
            title, note_md, tags, used_llm = (
                compiled.title, compiled.note, compiled.tags, True)
    except Exception:
        emit("llm_offline")
        title = Path(name).stem.replace("-", " ").replace("_", " ")
        note_md = (
            f"> ⚠ Local LLM offline — showing raw extracted text from "
            f"`{name}` ({extracted.kind}). Start Ollama to auto-compile.\n\n"
            + extracted.text
        )
        tags = []
        used_llm = False

    # 3) Optionally save straight into the vault. When the note came from
    #    schema-based extraction, persist the validated JSON alongside it
    #    so it can be viewed later (see GET /api/notes/{slug}/data).
    saved = None
    if save:
        emit("saving")
        note = vault.save(title, note_md, tags)
        saved = note.slug
        if extraction_info is not None:
            vault.save_data(note.slug, {
                "schema": schema_name,
                "source_filename": name,
                "valid": extraction_info["valid"],
                "errors": extraction_info["errors"],
                "data": extraction_info["data"],
            })
        emit("saved", slug=saved)

    result = {
        "filename": name,
        "kind": extracted.kind,
        "meta": extracted.meta,
        "title": title,
        "note": note_md,
        "tags": tags,
        "llm": used_llm,
        "chars": len(extracted.text),
        "saved": saved,
    }
    if extraction_info is not None:
        result["extraction"] = extraction_info
    return result


def _load_schema_or_404(schema_name: str) -> dict | None:
    if not schema_name:
        return None
    try:
        return schema_store.load(schema_name)
    except FileNotFoundError:
        raise HTTPException(404, f"Schema '{schema_name}' not found")


@app.post("/api/ingest")
async def ingest(
    files: list[UploadFile] = File(...),
    format_spec: str = Form(""),
    schema_name: str = Form(""),
    save: bool = Form(False),
):
    schema = _load_schema_or_404(schema_name)
    results = []
    for upload in files:
        data = await upload.read()
        name = upload.filename or "upload"
        results.append(_process_file(
            name, data, schema=schema, schema_name=schema_name,
            format_spec=format_spec, save=save,
        ))
    return {"results": results}


@app.post("/api/ingest/stream")
async def ingest_stream(
    files: list[UploadFile] = File(...),
    format_spec: str = Form(""),
    schema_name: str = Form(""),
    save: bool = Form(False),
):
    """Same as /api/ingest, but streams newline-delimited JSON progress
    events as each file is processed — so the UI can show live progress
    (which chunk is being summarised, composing, validating, saving...)
    instead of one opaque wait for slow local-model runs.
    """
    schema = _load_schema_or_404(schema_name)
    # Read all uploads up front: UploadFile's underlying stream isn't valid
    # once we start yielding a streaming response.
    file_payloads = [((u.filename or "upload"), await u.read()) for u in files]

    def emit_line(payload: dict) -> str:
        return json.dumps(payload) + "\n"

    async def event_source():
        loop = asyncio.get_event_loop()
        for name, data in file_payloads:
            yield emit_line({"event": "file_start", "filename": name})

            q: queue.Queue = queue.Queue()
            DONE = object()

            def on_progress(info, _q=q, _name=name):
                _q.put({"event": "progress", "filename": _name, **info})

            def worker(_q=q):
                try:
                    result = _process_file(
                        name, data, schema=schema, schema_name=schema_name,
                        format_spec=format_spec, save=save, on_progress=on_progress,
                    )
                    _q.put({"event": "file_done", "filename": name, "result": result})
                finally:
                    _q.put(DONE)

            threading.Thread(target=worker, daemon=True).start()

            while True:
                item = await loop.run_in_executor(None, q.get)
                if item is DONE:
                    break
                yield emit_line(item)

        yield emit_line({"event": "all_done"})

    return StreamingResponse(event_source(), media_type="application/x-ndjson")


# --------------------------------------------------------------------------
# Frontend (served last so /api/* takes precedence)
# --------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
