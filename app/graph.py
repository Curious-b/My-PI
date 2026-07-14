"""Build an Obsidian-style knowledge graph from the vault.

Nodes  = notes (and, optionally, tags)
Edges  = [[wiki-links]] between notes + note<->tag membership

The output is a plain JSON structure consumed by the force-directed graph
in the frontend (static/app.js).
"""
from __future__ import annotations

from .vault import Vault, slugify


def build_graph(vault: Vault, include_tags: bool = True) -> dict:
    notes = vault.all()

    # Map every title (case-insensitive) to its slug so links resolve even
    # when the user typed [[My Note]] but the file is my-note.md.
    title_to_slug: dict[str, str] = {}
    for note in notes:
        title_to_slug[note.title.lower()] = note.slug
        title_to_slug[note.slug.lower()] = note.slug

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_edges: set[tuple[str, str]] = set()

    link_counts: dict[str, int] = {n.slug: 0 for n in notes}

    for note in notes:
        for target in note.links:
            target_slug = title_to_slug.get(target.lower())
            if target_slug is None:
                # Link to a note that doesn't exist yet ("orphan link").
                target_slug = slugify(target)
                if target_slug not in link_counts:
                    nodes.append({
                        "id": f"note:{target_slug}",
                        "label": target,
                        "type": "missing",
                        "slug": target_slug,
                    })
                    link_counts[target_slug] = 0
            key = (note.slug, target_slug)
            if key not in seen_edges and note.slug != target_slug:
                seen_edges.add(key)
                edges.append({
                    "source": f"note:{note.slug}",
                    "target": f"note:{target_slug}",
                    "type": "link",
                })
                link_counts[target_slug] = link_counts.get(target_slug, 0) + 1
                link_counts[note.slug] = link_counts.get(note.slug, 0) + 1

    for note in notes:
        nodes.append({
            "id": f"note:{note.slug}",
            "label": note.title,
            "type": "note",
            "slug": note.slug,
            "tags": note.tags,
            "degree": link_counts.get(note.slug, 0),
        })

    if include_tags:
        tag_nodes: set[str] = set()
        for note in notes:
            for tag in note.tags:
                tag_id = f"tag:{tag}"
                if tag_id not in tag_nodes:
                    tag_nodes.add(tag_id)
                    nodes.append({"id": tag_id, "label": f"#{tag}", "type": "tag"})
                edges.append({
                    "source": f"note:{note.slug}",
                    "target": tag_id,
                    "type": "tag",
                })

    return {"nodes": nodes, "edges": edges}
