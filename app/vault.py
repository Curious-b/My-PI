"""The vault: reading/writing Markdown notes and parsing their structure.

A "note" is a Markdown file on disk. Notes may contain:
  * YAML frontmatter (--- ... ---) with optional `tags:` and `title:`
  * Obsidian-style wiki-links: [[Other Note]] or [[Other Note|alias]]
  * #hashtags anywhere in the body

Everything here is pure-Python and has no heavy dependencies, so the vault,
search index and graph all work even before you install Ollama/DSPy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

WIKILINK_RE = re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\[\]]+?))?\]\]")
HASHTAG_RE = re.compile(r"(?:^|\s)#([A-Za-z0-9_\-/]+)")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def slugify(name: str) -> str:
    """Turn a note title into a safe, stable filename stem."""
    slug = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "-")
    return re.sub(r"-{2,}", "-", slug) or "untitled"


@dataclass
class Note:
    """An in-memory representation of one Markdown note."""

    slug: str
    title: str
    body: str
    path: Path
    tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)  # titles this note points to
    modified: float = 0.0

    def to_summary(self) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "tags": self.tags,
            "links": self.links,
            "modified": self.modified,
        }

    def to_dict(self) -> dict:
        data = self.to_summary()
        data["body"] = self.body
        return data


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Very small YAML-ish frontmatter parser (title + tags only)."""
    meta: dict = {}
    match = FRONTMATTER_RE.match(text)
    if not match:
        return meta, text
    block = match.group(1)
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "tags":
            value = value.strip("[]")
            meta["tags"] = [t.strip().strip("'\"") for t in re.split(r"[,\s]+", value) if t.strip()]
        elif key in {"title", "aliases"}:
            meta[key] = value.strip("'\"")
    return meta, text[match.end():]


class Vault:
    """Manages the collection of notes on disk."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- paths ---------------------------------------------------------------
    def path_for(self, slug: str) -> Path:
        return self.root / f"{slug}.md"

    # -- read ----------------------------------------------------------------
    def _read_file(self, path: Path) -> Note:
        text = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)

        title = meta.get("title") or path.stem.replace("-", " ")
        tags = list(meta.get("tags", []))
        for tag in HASHTAG_RE.findall(body):
            if tag not in tags:
                tags.append(tag)

        links: list[str] = []
        for target, _alias in WIKILINK_RE.findall(body):
            target = target.strip()
            if target and target not in links:
                links.append(target)

        return Note(
            slug=path.stem,
            title=title,
            body=body,
            path=path,
            tags=tags,
            links=links,
            modified=path.stat().st_mtime,
        )

    def get(self, slug: str) -> Note | None:
        path = self.path_for(slug)
        return self._read_file(path) if path.exists() else None

    def all(self) -> list[Note]:
        notes = [self._read_file(p) for p in sorted(self.root.glob("*.md"))]
        return notes

    def iter_titles(self) -> Iterable[str]:
        for note in self.all():
            yield note.title

    # -- write ---------------------------------------------------------------
    def save(self, title: str, body: str, tags: list[str] | None = None,
             slug: str | None = None) -> Note:
        slug = slug or slugify(title)
        path = self.path_for(slug)
        tags = tags or []

        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        frontmatter = [
            "---",
            f"title: {title}",
            f"tags: [{', '.join(tags)}]",
            f"updated: {stamp}",
            "---",
            "",
        ]
        path.write_text("\n".join(frontmatter) + body.rstrip() + "\n", encoding="utf-8")
        return self._read_file(path)

    def delete(self, slug: str) -> bool:
        path = self.path_for(slug)
        if path.exists():
            path.unlink()
            return True
        return False
