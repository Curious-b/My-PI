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

    return AskWiki(), DraftNote()


# Lazily-instantiated singletons.
_ask_wiki = None
_draft_note = None


def _ensure_modules():
    global _ask_wiki, _draft_note
    ok, err = configure_lm()
    if not ok:
        raise RuntimeError(err)
    if _ask_wiki is None or _draft_note is None:
        _ask_wiki, _draft_note = _build_modules()
    return _ask_wiki, _draft_note


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
    ask_wiki, _ = _ensure_modules()
    context = _format_context(hits)
    pred = ask_wiki(question=question, context=context)
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
    _, draft = _ensure_modules()
    context = _format_context(hits)
    pred = draft(topic=topic, format_spec=format_spec, context=context)
    raw_tags = getattr(pred, "tags", "") or ""
    tags = [t.strip().lstrip("#") for t in raw_tags.replace("\n", ",").split(",") if t.strip()]
    return Draft(note=pred.note, tags=tags[:6])
