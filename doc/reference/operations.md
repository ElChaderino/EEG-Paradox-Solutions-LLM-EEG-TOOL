# Technical Reference — Operations

## Objective

Procedures for scheduling, backup, monitoring, and upgrade.

## Scheduling

| Job | Command | Typical schedule |
|-----|---------|------------------|
| Reflection | `python scripts\reflect.py` | Daily local time (e.g. 03:30) |
| API | From source: `python run_server.py` or `uvicorn …` (see below). **Desktop (Tauri):** `paradox-api.exe` sidecar started by the app after setup; bundle includes `eeg-worker/paradox-eeg-worker.exe` when built with `scripts/build_release.ps1`. | At logon or always-on server |
| Ollama | OS service / user startup | Before Paradox |

Use **Task Scheduler** on Windows. Set “Start in” directory to repository root when using relative paths in auxiliary scripts.

## Service wrapping (optional)

Tools such as NSSM or WinSW **may** wrap:

```
uvicorn hexnode.api.main:app --host 0.0.0.0 --port 8765
```

**Shall:** Run under a dedicated service account with minimal privileges if exposed beyond localhost.

## Backup

**Critical paths:**

- `data/chroma/`
- `data/vault/`

**Procedure:**

1. Stop API or ensure low write volume.
2. Copy directories to backup media.
3. Verify restore on a non-production machine periodically.

**Shall not** assume cloud sync handles SQLite/Chroma files safely during active writes without snapshots.

## Monitoring

**Minimal:**

- `GET /health` on interval from an external monitor (`ollama_ok`, `eeg_subprocess` if you run EEG jobs).
- Disk free space on volume holding `data/` and Ollama models.

**Logs:**

- Uvicorn access logs if enabled.
- Application logger `hexnode` for startup and ingest messages.

## Upgrade

**From source**

1. Pull or replace source tree.
2. `pip install -e ".[discord]"` (and `.[eeg]` if you run EEG jobs without the frozen worker) to refresh deps.
3. `cd web && npm install && npm run build` if UI changed.
4. Review `CHANGELOG.md` and `doc/README.md` for breaking changes.
5. Restart API.

**Desktop installer**

1. Build a new release with `scripts/build_release.ps1` (or install a vendor build whose version matches `VERSION` / filenames).
2. Run the new MSI/NSIS installer over the old install; confirm `GET /health` → `eeg_subprocess.bundled_worker` if you rely on bundled EEG visualization.
3. **v0.3.2+:** If interactive Plotly HTML (traceroute, 3D scalp, LORETA, trace viewer, microstate explorer) was missing on an older installer, upgrade ensures the EEG worker bundles **`orjson`** and uses UTF-8 subprocess I/O; run a **new** EEG job after upgrade (old job folders are not regenerated).

## Rollback

Maintain previous `data/chroma` backup before migrations that re-embed or rebuild indices.

## Incident response (lightweight)

If API is exposed and abused:

1. Stop listener.
2. Rotate Discord token if applicable.
3. Review firewall rules.
4. Restore Chroma from backup if integrity suspected.

## Related

- `user/03-daily-operation.md`
- `user/07-troubleshooting.md`
