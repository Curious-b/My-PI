"""FastAPI application — the private LLM Wiki server.

Bound to 127.0.0.1 by default (see config), so it is never exposed to the
network. Serves a single-page frontend plus a small JSON API.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .graph import build_graph
from .llm import llm_status
from .models import GenerateIn, NoteIn, QueryIn
from .retrieval import get_retriever
from .vault import Vault, slugify

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="My-PI — Private LLM Wiki", version="0.1.0")

vault = Vault(settings.vault_dir)


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
# Frontend (served last so /api/* takes precedence)
# --------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
