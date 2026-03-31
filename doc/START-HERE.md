# Start here — pick your path

Paradox Solutions LLM is documented in this `doc/` folder. Use the section that matches **what you are trying to do**.

## I only want to use the app (chat, upload files, no coding)

1. [User 01 — Prerequisites](user/01-prerequisites.md) — hardware, Ollama, models  
2. [User 02 — Installation](user/02-installation.md) — Python venv, `.env`, web dependencies  
3. [User 03 — Daily operation](user/03-daily-operation.md) — launch scripts, ports, stopping cleanly  
4. [User 04 — Web console](user/04-web-console.md) — using the Next.js UI  
5. [User 09 — EEG research](user/09-eeg-research.md) — uploads, analysis jobs, dashboards, clinical HTML (if you use EEG)

If you run the **Windows desktop build** (Tauri) instead of the browser: [User 08 — Desktop app (Tauri)](user/08-desktop-tauri.md). The shipped installer bundles the API and the **EEG worker** so clinical visualization jobs do not require a separate Python science stack on the machine (see [User 09 — EEG research](user/09-eeg-research.md)).

## I install or maintain it for someone else (operator / IT)

Same order as above, then add:

- [User 05 — Memory, ingest, reflection](user/05-memory-ingest-reflection.md)  
- [User 06 — Integrations](user/06-integrations.md) — SearXNG, Skye, Discord  
- [User 07 — Troubleshooting](user/07-troubleshooting.md)  
- [Reference — Operations](reference/operations.md) — scheduling, backups  

## I change code or build from source (developer)

1. [00 — Overview](00-overview.md) — architecture in one pass  
2. [Developer 01 — Repository structure](developer/01-repository-structure.md)  
3. [Developer 02 — Dev environment](developer/02-dev-environment.md) — API reload, web, optional Tauri  
4. [Developer 03 — Architecture](developer/03-architecture.md)  
5. [Developer 04 — Tools and registry](developer/04-tools-and-registry.md) when adding agent tools  
6. [Developer 05 — Agent and prompts](developer/05-agent-and-prompts.md)  
7. [Developer 06 — Frontend](developer/06-frontend.md)  

## I integrate over HTTP or automate the API (integrator)

- [Reference — REST API](reference/rest-api.md) — includes `/eeg/*` job and output routes  
- [Reference — Agent contract](reference/agent-contract.md)  
- [Reference — Tools catalog](reference/tools-catalog.md)  
- [Reference — Security](reference/security.md)  

## Everyone

- [Glossary](glossary.md)  
- [Full index](README.md) — complete document map  

The repository root [README.md](../README.md) is a short quick start; **this folder is the detailed specification.**
