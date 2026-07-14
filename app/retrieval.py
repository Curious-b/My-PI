"""Retrieval layer for RAG.

Preferred backend: ChromaDB + sentence-transformers (open-source, local, free).
Fallback backend: a pure-Python TF-IDF-ish keyword search that needs no
dependencies at all — so the app is useful the moment you clone it.

Both backends return the same shape: a list of (Note, score) style dicts.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .config import settings
from .vault import Note, Vault

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@dataclass
class Hit:
    slug: str
    title: str
    snippet: str
    score: float


class KeywordRetriever:
    """Dependency-free TF-IDF cosine search. Always available."""

    def __init__(self, vault: Vault):
        self.vault = vault

    def search(self, query: str, k: int = 5) -> list[Hit]:
        notes = self.vault.all()
        if not notes:
            return []

        docs = [_tokenize(f"{n.title} {n.body}") for n in notes]
        df: Counter = Counter()
        for doc in docs:
            df.update(set(doc))
        n_docs = len(docs)
        idf = {term: math.log((1 + n_docs) / (1 + df[term])) + 1 for term in df}

        def vector(tokens: list[str]) -> dict[str, float]:
            tf = Counter(tokens)
            return {t: (c / len(tokens)) * idf.get(t, 0.0) for t, c in tf.items()}

        q_vec = vector(_tokenize(query))
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

        hits: list[Hit] = []
        for note, doc in zip(notes, docs):
            d_vec = vector(doc)
            d_norm = math.sqrt(sum(v * v for v in d_vec.values())) or 1.0
            dot = sum(q_vec.get(t, 0.0) * v for t, v in d_vec.items())
            score = dot / (q_norm * d_norm)
            if score > 0:
                hits.append(Hit(note.slug, note.title, _snippet(note, query), score))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]


class VectorRetriever:
    """ChromaDB + local sentence-transformers embeddings (semantic search)."""

    def __init__(self, vault: Vault):
        self.vault = vault
        import chromadb
        from chromadb.utils import embedding_functions

        self._embed = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.embedding_model
        )
        self._client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        self._collection = self._client.get_or_create_collection(
            name="notes", embedding_function=self._embed
        )

    def reindex(self) -> int:
        """Rebuild the vector index from the current vault contents."""
        notes = self.vault.all()
        # Chroma has no cheap "clear", so recreate the collection.
        try:
            self._client.delete_collection("notes")
        except Exception:
            pass
        self._collection = self._client.get_or_create_collection(
            name="notes", embedding_function=self._embed
        )
        if not notes:
            return 0
        self._collection.add(
            ids=[n.slug for n in notes],
            documents=[f"{n.title}\n\n{n.body}" for n in notes],
            metadatas=[{"title": n.title} for n in notes],
        )
        return len(notes)

    def search(self, query: str, k: int = 5) -> list[Hit]:
        if self._collection.count() == 0:
            self.reindex()
        if self._collection.count() == 0:
            return []
        res = self._collection.query(query_texts=[query], n_results=k)
        hits: list[Hit] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for slug, doc, meta, dist in zip(ids, docs, metas, dists):
            score = 1.0 / (1.0 + float(dist))  # cosine distance -> similarity-ish
            title = (meta or {}).get("title", slug)
            snippet = doc[:280].replace("\n", " ")
            hits.append(Hit(slug, title, snippet, score))
        return hits


def _snippet(note: Note, query: str, width: int = 240) -> str:
    body = note.body.replace("\n", " ")
    q_tokens = _tokenize(query)
    lowered = body.lower()
    idx = -1
    for tok in q_tokens:
        idx = lowered.find(tok)
        if idx != -1:
            break
    if idx == -1:
        return body[:width].strip()
    start = max(0, idx - width // 3)
    return ("…" if start > 0 else "") + body[start:start + width].strip() + "…"


def get_retriever(vault: Vault):
    """Return the best available retriever, preferring semantic search."""
    try:
        return VectorRetriever(vault)
    except Exception:
        # chromadb / sentence-transformers not installed, or model download
        # blocked. Fall back to the always-available keyword retriever.
        return KeywordRetriever(vault)
