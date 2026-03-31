# User Manual 05 — Memory, Ingest, and Reflection

## Objective

Explain what is stored, where it lives, how files enter the system, and how nightly-style consolidation works.

## Memory collections

Three Chroma collections exist at runtime:

| Collection | Intended content |
|------------|------------------|
| `chat_history` | Conversation turns (user + Paradox), with interface metadata. |
| `documents` | Long-lived knowledge including reflection JSON text. |
| `library` | Chunks from ingested files and URLs. |

Detailed metadata fields: `reference/memory-and-chroma.md`.

## Scoring and recall

Retrieval ranks results using:

- Embedding similarity (distance).
- Stored **importance** and **manual_boost** metadata.
- **touch_ids** increments access counts and slightly raises importance on read.

The operator **shall** treat memory as **advisory context**, not a cryptographic audit log.

## Ingest queue

**Path:** `data/ingest_queue` (configurable via `INGEST_QUEUE`).

**Accepted types:** `.pdf`, `.txt`, `.md` (and `.markdown` if present).

**Mechanism:** Background watcher compares path + modification time keys to avoid duplicate processing in a single process lifetime. After successful chunking and embedding, content appears in `library`.

**Large files:** Chunking limits per-chunk size in code; extremely large PDFs may take noticeable time and GPU/CPU.

## Agent-driven ingest

The `ingest_document` tool accepts:

- A filesystem path (absolute or resolvable under the ingest queue).
- An `http://` or `https://` URL (fetch + text extraction).

## Vault artifacts

| Artifact | Path | Purpose |
|----------|------|---------|
| Reflection markdown | `data/vault/reflections/reflection_*.md` | Human-readable nightly or on-demand summaries. |
| Current focus | `data/vault/current_focus.md` | Injected into the agent system prompt on each run. |

## Reflection job

**Script:** `scripts/reflect.py`

**Effect:**

1. Samples each collection with a fixed semantic query string.
2. Calls the local chat model with JSON output schema (summary, patterns, gaps, next_focus, confidence).
3. Writes markdown and updates `current_focus.md`.
4. Adds a `documents` entry with `memory_type` appropriate to reflection.

**Scheduling:** Task Scheduler (Windows) or manual execution. The API process **need not** be running for `reflect.py` if Ollama and Chroma paths are consistent (script instantiates its own clients).

## Backup guidance

The operator **shall** back up:

- `data/chroma/` (vector store).
- `data/vault/` (human artifacts).

Quiesce heavy writes during copy if possible.

Next: `user/06-integrations.md`.
