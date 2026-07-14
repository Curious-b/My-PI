"""Tests for document extraction and the compile chunker (no LLM needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402  (skipped gracefully if unavailable via runner)

from app import ingest  # noqa: E402
from app.dspy_modules import _chunk  # noqa: E402


def test_extract_text():
    ex = ingest.extract("notes.txt", b"hello world")
    assert ex.kind == "text"
    assert ex.text == "hello world"


def test_extract_markdown():
    ex = ingest.extract("doc.md", b"# Title\n\nBody")
    assert ex.kind == "text"
    assert "Title" in ex.text


def test_extract_csv():
    ex = ingest.extract("data.csv", b"name,age\nAda,36\nAlan,41\n")
    assert ex.kind == "csv"
    assert "Ada | 36" in ex.text
    assert ex.meta["rows"] == 3


def test_unsupported_type():
    try:
        ingest.extract("photo.png", b"\x89PNG")
        raised = False
    except ingest.UnsupportedFile:
        raised = True
    assert raised


def test_truncation():
    big = b"a" * (ingest.MAX_CHARS + 5000)
    ex = ingest.extract("big.txt", big)
    assert len(ex.text) <= ingest.MAX_CHARS + 40
    assert ex.text.endswith("truncated…]")


def test_chunker_small():
    assert _chunk("short text", size=1000) == ["short text"]


def test_chunker_splits():
    text = "\n".join(f"paragraph number {i} " * 20 for i in range(50))
    chunks = _chunk(text, size=1000)
    assert len(chunks) > 1
    # No chunk is wildly over the size budget.
    assert all(len(c) < 2000 for c in chunks)
    # Reassembly preserves all content.
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")
