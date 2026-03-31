# Technical Reference — Memory and Chroma

## Objective

Define collections, metadata fields, ranking behavior, and operational constraints.

## Client configuration

**Class:** `MemoryStore` in `hexnode/memory_store.py`

**Backend:** `chromadb.PersistentClient` with path `settings.chroma_path`, telemetry disabled in settings object.

## Collections

| Name | Created at startup | Role |
|------|-------------------|------|
| `chat_history` | yes | Conversational memory. |
| `documents` | yes | Long-form knowledge and reflections. |
| `library` | yes | Ingested document chunks. |

## Metadata fields (intended)

Each add operation **shall** set at minimum:

| Key | Type | Meaning |
|-----|------|---------|
| `memory_type` | string | Subtype label (e.g. `chat`, `reflection`, `ingested_doc`). |
| `importance` | float | Base weight in \([0,1]\) scale (informal). |
| `access_count` | int | Number of recall touches. |
| `last_accessed` | string | ISO timestamp (UTC). |
| `manual_boost` | float | Operator or tool-driven boost. |
| `created` | string | ISO timestamp (UTC). |

Additional keys **may** appear via `extra_meta` (e.g. `interface`, `trace_id`, `source`, `filename`).

**Implementation note:** Chroma stores metadata as scalar types; do not nest objects in metadata.

## Embedding pipeline

1. Text → `OllamaClient.embed` using `settings.embed_model`.
2. Vector stored alongside document in `collection.add`.

**Invariant:** Changing `embed_model` without re-embedding **shall** be considered a breaking schema change for similarity quality.

## Query and ranking

**Method:** `MemoryStore.query(collection_name, query_text, top_k, memory_type_filter)`

1. Embed `query_text`.
2. For each target collection, run `collection.query` with embeddings.
3. For each hit, compute components: similarity `sim = 1/(1+dist)`; importance and manual_boost from metadata; recency from `last_accessed` via exponential decay (`memory_recency_half_life_days`; half-life `0` → neutral 0.5).
4. Blend: normalized weights `memory_w_*` applied to `(sim, importance, recency, manual_boost)` — see `blend_memory_score` in `memory_store.py`. Each hit includes `score_components` for debugging.
5. Merge multi-collection results; sort descending by `score`; truncate to `top_k`.

## Touch behavior

`touch_ids` loads metadata by id, increments `access_count`, updates `last_accessed`, slightly increases `importance` (capped at 1.0).

## Boost behavior

`boost_memory` increases `manual_boost` and `importance` subject to caps.

## Failure modes

- Corrupt Chroma directory: delete `data/chroma` only after backup — full re-ingest required.
- Concurrent file locking on Windows: see user troubleshooting.

## Related

- `reference/tools-catalog.md` — `query_memory`, `boost_memory`.
- `user/05-memory-ingest-reflection.md` — operator narrative.
