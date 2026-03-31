# User Manual 04 — Web Console

## Objective

Document the operator-facing behavior of the Next.js application in `web/`.

## Purpose of the console

The console is a **browser-based control surface**. It is not the authoritative security boundary; the API is. The console **shall** be used only against Paradox instances the operator trusts.

## Layout

1. **Header** — System nickname, health badge, HUD color toggle.
2. **Main panel (session)** — Chat transcript; messages from the user and from Paradox.
3. **Side column**
   - **Operating focus** — Text read from `GET /focus` (backed by `data/vault/current_focus.md`).
   - **System** — JSON from `GET /system/stats` (CPU, RAM, disk, GPU fields when available).
   - **Memory search** — Calls `POST /memory/query` with the operator’s semantic query string.
   - **Files** — Drag-and-drop upload, categorized lists, delete; routes EEG and documents per API rules.
   - **EEG Data** — Upload recordings, start `POST /eeg/process` jobs, poll status, open HTML/PNG outputs in-app or on disk. Full workflow: [User 09 — EEG research](09-eeg-research.md).

## Chat behavior

1. Operator enters text and sends (button or Enter).
2. Client issues `POST /agent` with body `{ "message": "<text>", "interface": "desktop" }`.
3. On success, the assistant bubble shows `answer`. Metadata line includes approximate confidence, `trace_id`, and whether Skye was used (`skye` suffix when escalated).

## HUD toggle

The **HUD** control cycles accent styling (cyan versus matrix-green remapping). Preference is stored in browser `localStorage` under key `paradox-hud-color`. This affects presentation only.

## Error display

Network or HTTP errors are shown inline in the chat as a Paradox message prefixed with `Error:`. **504** from `POST /agent` usually means Ollama did not respond within the read timeout (large model or overloaded GPU). The operator **shall** consult `user/07-troubleshooting.md` if errors persist.

## File ingest hint

The console displays a reminder path `data/ingest_queue`. That path is relative to the **API host’s** project root, not the browser machine, unless a shared filesystem maps them.

## Dependencies

The console requires:

- CORS allowance for its origin in `CORS_ORIGINS` on the API.
- Reachable `NEXT_PUBLIC_HEX_API` from the browser (same machine or routed LAN).

Next: `user/05-memory-ingest-reflection.md`. For EEG-specific UI and jobs, see `user/09-eeg-research.md`.
