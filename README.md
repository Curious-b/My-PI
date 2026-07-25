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
| **Upload PDF / Word / Excel → Markdown** | The *Upload* tab extracts text from your documents and DSPy compiles each into a clean, structured `.md` note (long files are map-reduced). |
| **Extract to *your* format, using *your* JSON Schema** | Upload your own JSON Schema file per document type; DSPy extracts exactly those fields, validates them, self-repairs invalid output, then renders the result to Markdown. |
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
- **Upload** – drop in **PDF, Word, Excel, CSV or text** files. My-PI extracts
  the content and DSPy compiles each into a structured Markdown note following
  your template. Long documents are summarised chunk-by-chunk, then composed.
  Without Ollama running you still get the raw extracted text back. Each file
  gets a **live progress card** — reading the file, splitting into chunks,
  summarising chunk *N*/*M*, composing/extracting, validating, saving — so
  you can see exactly what's happening instead of staring at a static spinner
  through a slow local-model run.

  **Bring your own JSON Schema — a two-step flow.** If you have a set of
  JSON Schema files (one per document type — e.g. `district-analysis.json`,
  `invoice.json`), upload them once via "+ Upload schema" in the Upload tab.
  Then, when uploading a matching document, pick that schema from the
  dropdown instead of typing a free-text template. Schema mode is
  deliberately **two explicit steps**, not one automatic conversion:

  1. **Extract.** My-PI asks the local LLM (via DSPy) to extract exactly the
     fields your schema defines, as JSON, validates the result (using
     `jsonschema`), and — if validation fails — automatically asks the
     model to repair it once. The result is shown as raw JSON, with:
     - **⬇ Download JSON** — save the extracted data as a `.json` file directly.
     - **👁 view schema** (next to the dropdown) — see the full schema you uploaded.
  2. **Convert to Markdown** — a separate button you click when you're
     ready. This step is pure, instant rendering (no LLM call): it turns
     the JSON into Markdown with **one clearly defined section per
     field**, in the exact order your schema declares its properties, using
     each property's `title` as the section heading. From there you can
     **⬇ Download Markdown** or **💾 Save to vault** (which also persists
     the validated JSON alongside the note as `<slug>.json`, viewable later
     via a "📄 extracted JSON" panel whenever you reopen that note).

  Your schema files are stored locally in `schemas/` (git-ignored, same
  privacy model as the vault) — nothing is invented on your behalf; the
  fields extracted, their order, and their section labels are exactly what
  you defined.

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
| POST | `/api/ingest` | upload documents → compiled Markdown notes; with `schema_name`, stops at validated JSON extraction (see `/api/render`) |
| POST | `/api/ingest/stream` | same as above, but streams live newline-delimited JSON progress events as each file is processed |
| POST | `/api/render` | convert a previously-extracted JSON object into a Markdown note (no LLM call — pure rendering), optionally saving it |
| GET | `/api/schemas` | list uploaded JSON Schema templates |
| GET | `/api/schemas/{name}` | view the full content of one schema |
| POST | `/api/schemas` | upload a JSON Schema file |
| DELETE | `/api/schemas/{name}` | remove a JSON Schema template |
| GET | `/api/notes/{slug}/data` | the validated JSON extracted for a note (if created via a schema) |
| GET | `/api/status` | vault + retriever + LLM health |

---

## ⚡ Making extraction faster
Uploading a large PDF runs several sequential local-model calls (summarise
each chunk, then compose/extract), which is inherently slower than a cloud
API — you're trading speed for privacy and cost. If it feels too slow:

1. **Use a smaller model.** This is the single biggest lever. An 8B model
   like `llama3.1` on a CPU-only machine can be genuinely slow. Try:
   ```bash
   ollama pull qwen2.5:3b     # or: llama3.2:3b, phi3:mini
   ```
   then set `LLM_MODEL=ollama_chat/qwen2.5:3b` in `.env` and restart. Smaller
   models are often 3–10x faster with little quality loss for extraction.
2. **Check you're not silently running on CPU** if you have a GPU — Ollama
   uses it automatically when available; `ollama ps` shows whether a model
   is running on GPU or CPU.
3. **Tune `CHUNK_SIZE`/`MAX_CHUNKS` in `.env`** (see `.env.example`). Fewer,
   larger chunks means fewer round-trips, but each call needs more of your
   model's context window — raise `CHUNK_SIZE` only if you know your model
   supports it, otherwise output can get silently truncated.
4. The per-chunk summarisation and JSON-repair steps already use
   `dspy.Predict` rather than `dspy.ChainOfThought` — no reasoning pass, so
   fewer tokens generated per call. This is built in, nothing to configure.

With the live progress cards (Upload tab), you can also now see *which*
step is slow — if it's stuck on "Summarizing chunk 1/8…", that's model
generation speed; if every step flashes by until "Composing," the document
was fast to read and the final compose call is the bottleneck.

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
