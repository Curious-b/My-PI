"""DSPy signatures & modules powering the two headline features:

  1. AskWiki  — Retrieval-Augmented question answering over your notes.
  2. DraftNote — Generate a new note in a *customized* format you specify.

DSPy handles prompting/reasoning declaratively via typed Signatures, so the
behaviour is easy to inspect, optimize, and swap models on. If DSPy or the
local model is unavailable, the callers degrade gracefully (see main.py).
"""
from __future__ import annotations

from dataclasses import dataclass

from .llm import configure_lm
from .retrieval import Hit
from .vault import Vault, Note


# --------------------------------------------------------------------------
# Signatures are only defined when DSPy is importable, to keep the module
# importable in environments where dspy isn't installed yet.
# --------------------------------------------------------------------------
def _build_modules():
    import dspy

    class AnswerFromNotes(dspy.Signature):
        """Answer the user's question using ONLY the provided notes.
        Cite the note titles you used. If the notes don't contain the answer,
        say so plainly instead of inventing facts."""

        context: str = dspy.InputField(desc="Relevant excerpts from the knowledge base")
        question: str = dspy.InputField()
        answer: str = dspy.OutputField(desc="A grounded answer that cites note titles")

    class ComposeNote(dspy.Signature):
        """Write a well-structured Markdown note about `topic`, weaving in any
        relevant `context` from the existing knowledge base. Follow the user's
        `format_spec` exactly (headings, sections, style). Add [[wiki-links]] to
        related notes where natural, and suggest 3-6 lowercase tags."""

        topic: str = dspy.InputField()
        format_spec: str = dspy.InputField(desc="The desired output template / format")
        context: str = dspy.InputField(desc="Related existing notes (may be empty)")
        note: str = dspy.OutputField(desc="The note body in Markdown, no frontmatter")
        tags: str = dspy.OutputField(desc="Comma-separated list of tags")

    class SummariseChunk(dspy.Signature):
        """Faithfully summarise one chunk of a larger document, preserving the
        key facts, figures, names and structure. Do not add anything not in the
        text."""

        source: str = dspy.InputField(desc="The source document's filename")
        chunk: str = dspy.InputField()
        summary: str = dspy.OutputField(desc="A dense factual summary of the chunk")

    class CompileNote(dspy.Signature):
        """Compile the extracted contents of an uploaded document into a single,
        clean, well-structured Markdown knowledge-base note. Follow the user's
        `format_spec`. Derive a concise descriptive title. Preserve important
        facts, figures and tables from the source; do not invent information.
        Add [[wiki-links]] where natural and suggest 3-6 lowercase tags."""

        source: str = dspy.InputField(desc="The source document's filename")
        content: str = dspy.InputField(desc="Extracted text (or summaries) of the document")
        format_spec: str = dspy.InputField(desc="The desired output template / format")
        title: str = dspy.OutputField(desc="A concise title for the note")
        note: str = dspy.OutputField(desc="The note body in Markdown, no frontmatter")
        tags: str = dspy.OutputField(desc="Comma-separated list of tags")

    class AskWiki(dspy.Module):
        def __init__(self):
            super().__init__()
            self.answer = dspy.ChainOfThought(AnswerFromNotes)

        def forward(self, question: str, context: str):
            return self.answer(question=question, context=context)

    class DraftNote(dspy.Module):
        def __init__(self):
            super().__init__()
            self.compose = dspy.ChainOfThought(ComposeNote)

        def forward(self, topic: str, format_spec: str, context: str):
            return self.compose(topic=topic, format_spec=format_spec, context=context)

    class CompileDoc(dspy.Module):
        def __init__(self):
            super().__init__()
            self.summarise = dspy.ChainOfThought(SummariseChunk)
            self.compile = dspy.ChainOfThought(CompileNote)

        def forward(self, source: str, content: str, format_spec: str):
            return self.compile(source=source, content=content, format_spec=format_spec)

    return {"ask": AskWiki(), "draft": DraftNote(), "compile": CompileDoc()}


# Lazily-instantiated singletons.
_modules: dict | None = None


def _ensure_modules():
    global _modules
    ok, err = configure_lm()
    if not ok:
        raise RuntimeError(err)
    if _modules is None:
        _modules = _build_modules()
    return _modules


def _format_context(hits: list[Hit]) -> str:
    if not hits:
        return "(no relevant notes found)"
    blocks = []
    for h in hits:
        blocks.append(f"### {h.title}\n{h.snippet}")
    return "\n\n".join(blocks)


@dataclass
class Answer:
    answer: str
    reasoning: str
    sources: list[dict]


def ask(question: str, hits: list[Hit]) -> Answer:
    modules = _ensure_modules()
    context = _format_context(hits)
    pred = modules["ask"](question=question, context=context)
    return Answer(
        answer=pred.answer,
        reasoning=getattr(pred, "reasoning", ""),
        sources=[{"slug": h.slug, "title": h.title, "score": round(h.score, 3)} for h in hits],
    )


@dataclass
class Draft:
    note: str
    tags: list[str]


def draft_note(topic: str, format_spec: str, hits: list[Hit]) -> Draft:
    modules = _ensure_modules()
    context = _format_context(hits)
    pred = modules["draft"](topic=topic, format_spec=format_spec, context=context)
    raw_tags = getattr(pred, "tags", "") or ""
    tags = [t.strip().lstrip("#") for t in raw_tags.replace("\n", ",").split(",") if t.strip()]
    return Draft(note=pred.note, tags=tags[:6])


# --- Document compilation -------------------------------------------------
def _chunk(text: str, size: int = 6000) -> list[str]:
    """Split text into ~size-char chunks on paragraph boundaries."""
    if len(text) <= size:
        return [text]
    chunks, current = [], []
    length = 0
    for para in text.split("\n"):
        if length + len(para) > size and current:
            chunks.append("\n".join(current))
            current, length = [], 0
        current.append(para)
        length += len(para) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


@dataclass
class Compiled:
    title: str
    note: str
    tags: list[str]


def compile_document(source: str, text: str, format_spec: str,
                     max_chunks: int = 8) -> Compiled:
    """Turn extracted document text into a structured Markdown note.

    For long documents this map-reduces: summarise each chunk, then compile the
    summaries into the final note. Bounded by `max_chunks` to keep it fast on
    CPU-only local models.
    """
    modules = _ensure_modules()
    compiler = modules["compile"]

    chunks = _chunk(text)
    if len(chunks) == 1:
        content = text
    else:
        summaries = []
        for chunk in chunks[:max_chunks]:
            pred = compiler.summarise(source=source, chunk=chunk)
            summaries.append(pred.summary)
        if len(chunks) > max_chunks:
            summaries.append("[…remaining sections omitted for length…]")
        content = "\n\n".join(summaries)

    pred = compiler(source=source, content=content, format_spec=format_spec)
    raw_tags = getattr(pred, "tags", "") or ""
    tags = [t.strip().lstrip("#") for t in raw_tags.replace("\n", ",").split(",") if t.strip()]
    title = (getattr(pred, "title", "") or source).strip()
    return Compiled(title=title, note=pred.note, tags=tags[:6])
