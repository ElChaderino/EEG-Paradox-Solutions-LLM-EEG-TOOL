# Technical Reference — REST API

## Objective

Specify HTTP routes exposed by `hexnode.api.main:app`. Base URL: `http://<host>:<port>/` per configuration.

## Common

- **Content-Type** for POST bodies: `application/json` unless noted.
- **Errors:** FastAPI returns standard HTTP status codes; bodies may be JSON detail strings.

---

### `GET /health`

**Purpose:** Liveness, Ollama reachability, EEG norms add-on, EEG subprocess resolution, and optimization flags.

**Response (200):** JSON including at least:

| Field | Type | Notes |
|-------|------|--------|
| `status` | string | `ok` when Ollama `/api/tags` succeeds; else `degraded`. |
| `ollama` | boolean | Reachability of `OLLAMA_BASE`. |
| `chroma_path` | string | Persistent Chroma directory. |
| `eeg_norms_addon` | object | Installed Cuban norms DLC metadata (see `user/10-eeg-norms-addon.md`). |
| `eeg_subprocess` | object | `ok`, `python` path, `frozen`, `bundled_worker`, `viz_script_found`, optional `warning` / `error`. |
| `optimizations` | object | Flash attention, KV cache type, embed quantize summary. |

---

### `POST /agent`

**Purpose:** Run full agent loop and persist chat turn.

**Request body:**

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `message` | string | yes | 1–32000 chars |
| `interface` | string | no | Stored in metadata; default `api` |

**Response (200):**

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | Final natural language response. |
| `confidence` | number | Scalar confidence. |
| `steps` | array | Per-step records (thought, action, observation subset). |
| `trace_id` | string | Correlation id for logs. |
| `escalated_skye` | boolean | Whether Skye path ran. |
| `symbolic_hints` | string \| null | Injected neuro-symbolic hint block (if any rules matched). |
| `react_version` | string | Agent loop version tag (e.g. `v2`). |

**Errors:**

| Code | Meaning |
|------|---------|
| `503` | Memory or Ollama client not initialized. |
| `502` | Ollama returned an error response (`OllamaChatError`); detail includes server message when available. |
| `504` | HTTP read timeout waiting for Ollama (model load or overload); retry later. |

---

### `POST /memory/query`

**Purpose:** Semantic search without agent.

**Request body:**

| Field | Type | Required |
|-------|------|----------|
| `query` | string | yes |
| `collection` | string \| null | no — one of `chat_history`, `documents`, `library`, or null for all |
| `top_k` | int \| null | no |

**Response (200):** `{ "hits": [ ... ] }` — each hit includes `id`, `document`, `metadata`, `distance`, `score`, `collection`.

---

### `GET /system/stats`

**Purpose:** Host metrics (psutil + optional GPU).

**Response (200):** `{ "stats": { ... }, "gpu": { ... } }`

`gpu` may be empty object if `nvidia-smi` fails.

**Errors:** `503` not ready; `500` tool failure.

---

### `GET /focus`

**Purpose:** Read operating focus text.

**Response (200):** `{ "current_focus": "string" }`

---

### `GET /tools`

**Purpose:** Introspect registered tools.

**Response (200):** `{ "tools": [ { "name", "description" }, ... ] }`

---

### `POST /ingest/path`

**Purpose:** Ingest a single file from explicit path (operator tool).

**Request body:** `{ "path": "string" }` — absolute or resolvable path on API host.

**Response (200):** `{ "chunks": number, "path": "string" }`

**Errors:** `400` invalid path or ingest error; `503` not ready.

---

## EEG workspace and jobs

Base paths use `settings.eeg_workspace` (default under `data/eeg_workspace/`). Job artifacts live in `eeg_workspace/output/<job_id>/`.

### `GET /eeg/outputs`

**Purpose:** List files in the shared global output directory (`eeg_workspace/output/`), newest first.

**Response (200):** `{ "files": [ { "name", "type", "size", "modified" }, ... ] }`  
`type` is one of `html`, `image`, `json`, `data`, `other` (derived from extension).

---

### `GET /eeg/outputs/{filename}`

**Purpose:** Download or view one file from the global output directory. Path traversal is rejected (`403`).

**Response:** `FileResponse` with MIME by extension (HTML, images, JSON, `.fif` as octet-stream).

---

### `POST /eeg/process`

**Purpose:** Upload one EEG file and start a **background processing job** (pipeline script, clinical scripts, visualization orchestrator including NetOps when available).

**Request:** `multipart/form-data`

| Field | Type | Default | Notes |
|-------|------|---------|--------|
| `file` | file | required | `.edf`, `.bdf`, `.set`, `.fif`, `.vhdr`, `.cnt`, etc. |
| `condition` | string | `EC` | Passed into generated pipeline config. |
| `output_mode` | string | `standard` | Pipeline output mode. |
| `remontage_ref` | string | `""` | Optional remontage hint. |

**Response (200):** `{ "job_id", "status": "queued", "filename" }`

**Errors:** `400` unsupported extension or file too large (limit configured on API).

---

### `GET /eeg/jobs`

**Purpose:** List all known jobs (in-memory cache merged with disk `_job.json` under each job dir).

**Response (200):** `{ "jobs": [ { "id", "filename", "status", "progress", "condition", "output_mode", "started", "output_count", "error" }, ... ] }`  
(Exact keys may grow; the UI uses `condition` and `output_mode` for badges.)

---

### `GET /eeg/jobs/{job_id}`

**Purpose:** Job detail for polling UI.

**Response (200):** `id`, `filename`, `status`, `progress`, `messages` (tail), `started`, `output_files`, `metrics`, `error`.

**Errors:** `404` unknown job.

---

### `GET /eeg/jobs/{job_id}/files/{filename}`

**Purpose:** Serve a single artifact from the job directory. HTML responses include relaxed iframe headers for in-app preview.

**Errors:** `403` path escape; `404` missing file or job.

---

### `POST /eeg/jobs/{job_id}/delete`

**Purpose:** Remove the job directory tree.

**Response (200):** `{ "status": "deleted", "id" }`

**Errors:** `404` if directory absent.

---

### `POST /workspace/open`

**Purpose:** Open the EEG workspace **output** folder in the OS file manager (Windows: Explorer).

**Response (200):** `{ "status": "opened", "path" }`

**Errors:** `500` if spawn fails.

---

## Related

- `user/09-eeg-research.md` — operator-oriented EEG workflow.
- `reference/agent-contract.md` — agent semantics behind `/agent`.
- `reference/security.md` — exposure guidance.
