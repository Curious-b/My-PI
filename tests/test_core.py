"""Tests for the dependency-free core: vault parsing, graph, keyword search.

These run without DSPy / Ollama / Chroma installed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.vault import Vault, slugify, WIKILINK_RE  # noqa: E402
from app.graph import build_graph  # noqa: E402
from app.retrieval import KeywordRetriever  # noqa: E402


def make_vault(tmp_path):
    v = Vault(tmp_path)
    v.save("Alpha", "Alpha links to [[Beta]] and mentions #python.", tags=["core"])
    v.save("Beta", "Beta talks about [[Alpha]] and databases. #python #db")
    v.save("Gamma", "Gamma is a lonely note about cooking recipes.")
    return v


def test_slugify():
    assert slugify("Hello World!") == "Hello-World"
    assert slugify("  spaced  out ") == "spaced-out"
    assert slugify("###") == "untitled"


def test_wikilink_regex():
    assert WIKILINK_RE.findall("see [[Note A]] and [[Note B|alias]]") == [
        ("Note A", ""), ("Note B", "alias")]


def test_save_and_read(tmp_path):
    v = make_vault(tmp_path)
    note = v.get("Alpha")
    assert note is not None
    assert note.title == "Alpha"
    assert "Beta" in note.links
    assert "python" in note.tags
    assert "core" in note.tags


def test_graph_edges(tmp_path):
    v = make_vault(tmp_path)
    g = build_graph(v, include_tags=True)
    ids = {n["id"] for n in g["nodes"]}
    assert "note:Alpha" in ids and "note:Beta" in ids
    link_edges = [e for e in g["edges"] if e["type"] == "link"]
    pairs = {(e["source"], e["target"]) for e in link_edges}
    assert ("note:Alpha", "note:Beta") in pairs
    assert ("note:Beta", "note:Alpha") in pairs
    assert any(n["type"] == "tag" and n["label"] == "#python" for n in g["nodes"])


def test_keyword_search(tmp_path):
    v = make_vault(tmp_path)
    hits = KeywordRetriever(v).search("databases", k=3)
    assert hits
    assert hits[0].title == "Beta"


def test_delete(tmp_path):
    v = make_vault(tmp_path)
    assert v.delete("Gamma") is True
    assert v.get("Gamma") is None
    assert v.delete("Gamma") is False


def test_companion_data_roundtrip(tmp_path):
    v = make_vault(tmp_path)
    assert v.get_data("Alpha") is None  # nothing saved yet

    payload = {"schema": "district", "data": {"district": "Mysuru"}}
    v.save_data("Alpha", payload)
    assert v.get_data("Alpha") == payload

    # Overwriting replaces, not merges.
    v.save_data("Alpha", {"data": {"district": "Bengaluru"}})
    assert v.get_data("Alpha") == {"data": {"district": "Bengaluru"}}


def test_delete_note_removes_companion_data(tmp_path):
    v = make_vault(tmp_path)
    v.save_data("Alpha", {"data": {"x": 1}})
    assert v.data_path_for("Alpha").exists()

    v.delete("Alpha")
    assert v.get_data("Alpha") is None
    assert not v.data_path_for("Alpha").exists()
