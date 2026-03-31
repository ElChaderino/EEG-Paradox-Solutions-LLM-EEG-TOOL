# User Manual 01 — Prerequisites

## Objective

Establish the minimum environment in which Paradox **shall** operate without undefined behavior. This document lists hardware expectations, software dependencies, and external services.

## Hardware

| Resource | Minimum | Notes |
|----------|---------|--------|
| RAM | 16 GB | Larger models and Chroma benefit from headroom. |
| GPU | Optional | Ollama uses NVIDIA GPUs when drivers permit; CPU-only mode is slower but valid. |
| Disk | 20 GB free | Models dominate storage; Chroma grows with ingested content. |

## Operating system

- **Supported:** Windows 10 (22H2 or newer) or Windows 11.
- **Assumption:** PowerShell or Command Prompt for commands in companion documents.

## Required software

1. **Python** — Version 3.11 or newer (3.12 supported). The operator **shall** prefer an isolated virtual environment for this project.
2. **Ollama for Windows** — Installed and able to respond at `http://127.0.0.1:11434` when the daemon is running.
3. **Node.js** — Current LTS recommended, for building and running the `web/` client.

## Model artifacts

Before first successful `/agent` call, the operator **shall** pull at least:

- One **chat** model matching `CHAT_MODEL` in `.env` (default **`qwen3:8b`** in `hexnode.config`; see `.env.example`).
- If `FAST_MODEL` is set in `.env`, pull that model too (example: **`phi4-mini`** for quick routing tasks).
- One **embedding** model matching `EMBED_MODEL` (default **`nomic-embed-text`**).

If **Skye** escalation is enabled (`SKYE_URL` set), pull `SKYE_MODEL` as well (default name in config: **`mistral-small:22b`** — often run on a second machine with Ollama).

**Example pulls** (run one model per command):

```powershell
ollama pull qwen3:8b
ollama pull phi4-mini
ollama pull nomic-embed-text
ollama pull mistral-small:22b
```

VRAM limits **shall** be respected: quantized or smaller models may be required on 6–8 GB GPUs. Optional coding-oriented local swap: `qwen2.5-coder:7b` (see `.env.example` comments).

## Optional services

| Service | Purpose | If absent |
|---------|---------|-----------|
| SearXNG | Private web search via `web_search` tool | Tool returns configuration error; agent may use other tools. |
| Remote Ollama (Skye) | Heavy model second pass | Escalation skipped; local answer only. |
| Discord | Channel bridge via script or `send_discord_message` | Features inert until token and channel configured. |

## Network posture

- Default API bind address `0.0.0.0` exposes the service on all interfaces. On untrusted networks the operator **shall** restrict via Windows Firewall or bind to `127.0.0.1` only.
- Discord and Skye require outbound HTTPS or LAN HTTP as applicable.

## Verification checklist

- [ ] `python --version` reports ≥ 3.11.
- [ ] `ollama list` shows required models.
- [ ] `nvidia-smi` succeeds if GPU acceleration is expected (optional).

Next: `user/02-installation.md`.
