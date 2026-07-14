# My-PI 🧠 — Your Private LLM Wiki

A **local-first, zero-cost "second brain."** Capture Markdown notes, link them
Obsidian-style, explore them as an interactive knowledge graph, then **query**
your knowledge base or **generate new notes in any format you like** — all
powered by **open-source models running on your own machine** via
[Ollama](https://ollama.com) and orchestrated with the
[**DSPy**](https://github.com/stanfordnlp/dspy) framework.

> Private by design: your notes live only in the local `vault/` folder, the
> server binds to `127.0.0.1`, the whole vault is git-ignored, and no data is
> ever sent to any cloud service. **No API keys. No subscriptions. No cost.**

---

## ✨ Features

| Requirement you asked for | How My-PI delivers it |
|---|---|
| Open-source models, **no money** | Ollama (Llama 3.1 / Qwen / Mistral …) + local `sentence-transformers` embeddings. 100% free & offline. |
| **Keep data private** | Notes are plain files in `vault/`, git-ignored. Server is localhost-only. No telemetry. |
| **Obsidian-style graph view** | Custom force-directed canvas graph — drag, zoom, click a node to open the note. Notes, `[[links]]`, and `#tags` all visualised. |
| **DSPy framework** | Typed DSPy `Signature`s + `ChainOfThought` modules power both Q&A and note generation (`app/dspy_modules.py`). |
| **Generate files in a custom format** | Give a template in the *Generate* tab; the model fills it in and (optionally) saves a new linked note. |
| **Query the knowledge base** | Retrieval-Augmented Generation over your notes in the *Ask* tab, with cited sources. |
| A brain that **keeps growing** | Just keep adding Markdown files — the index, search, and graph update automatically. |

---

## 🚀 Quick start

### 1. Install Ollama and pull an open-source model (free)
```bash
# https://ollama.com/download
ollama pull llama3.1        # or: qwen2.5, mistral, phi3 …
```

### 2. Run My-PI
```bash
./run.sh                    # creates a venv, installs deps, starts the server
```
Then open **http://127.0.0.1:8000**.

> `run.sh` installs everything from `requirements.txt`. Prefer manual setup?
> ```bash
> python3 -m venv .venv && source .venv/bin/activate
> pip install -r requirements.txt
> uvicorn app.main:app --reload
> ```

Don't have Ollama yet? The app still runs — the **graph, notes, and keyword
search work with zero extra setup**; the *Ask* and *Generate* features light up
once Ollama is available.

---

## 🖥️ Using it

- **Graph** – your whole vault as a living map. Blue = notes, purple = tags,
  red = links to notes you haven't written yet. Click a node to open it.
- **Note** – a Markdown editor with live preview and clickable `[[wiki-links]]`.
- **Ask** – ask a natural-language question; DSPy retrieves the most relevant
  notes and answers with citations.
- **Generate** – enter a topic and a **custom template**; the model drafts a
  note in that exact format, suggests tags, and can save it straight to the vault.

---

## 🧩 Architecture

```
Browser (static/) ──HTTP──> FastAPI (app/main.py)
                                │
     ┌──────────────────────────┼─────────────────────────────┐
     ▼                          ▼                              ▼
 Vault (app/vault.py)     Retrieval (app/retrieval.py)   DSPy (app/dspy_modules.py)
 Markdown files,          Chroma + local embeddings       ChainOfThought modules
 [[links]], #tags         (keyword fallback)              → Ollama (open-source LLM)
     │
     ▼
 Graph (app/graph.py) ──> nodes + edges JSON ──> canvas force-graph (static/app.js)
```

**Tech:** Python · FastAPI · DSPy · Ollama · ChromaDB · sentence-transformers ·
vanilla JS canvas (no frontend build step, no CDN).

### Swapping the model
Set it in `.env` (copy from `.env.example`):
```
LLM_MODEL=ollama_chat/qwen2.5
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

---

## 🔌 API (all local)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/notes` · `/api/notes/{slug}` | list / read notes |
| POST · PUT · DELETE | `/api/notes` … | create / update / delete |
| GET | `/api/graph?tags=true` | graph nodes + edges |
| GET | `/api/search?q=…` | retrieval only (no LLM) |
| POST | `/api/query` | RAG question answering |
| POST | `/api/generate` | generate a note in a custom format |
| GET | `/api/status` | vault + retriever + LLM health |

---

## 🧪 Tests
The dependency-free core (vault parsing, graph building, keyword search) is
covered by `tests/test_core.py`:
```bash
pip install pytest && pytest -q
```

---

## 🔒 Privacy checklist
- [x] Notes stored locally in `vault/` (git-ignored)
- [x] Server binds to `127.0.0.1` only
- [x] Models run locally via Ollama — prompts never leave your machine
- [x] Embeddings computed locally — no external API
- [x] No analytics, no accounts, no cloud
