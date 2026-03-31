# Technical Reference — Security Model

## Objective

State assumptions, threats, and controls. This is not a formal certification document.

## Trust boundaries

| Boundary | Trust assumption |
|----------|------------------|
| API listener | Trusted clients on allowed networks only. |
| Ollama | Local or LAN; model execution equals arbitrary code class risk per Ollama project guidance. |
| Chroma files | Readable by OS users with filesystem access. |
| Discord token | Secret; grants bot capabilities per Discord ACLs. |

## Authentication and authorization

**Current state:** No API keys, no OAuth. **Implication:** Anyone who can reach `PORT` can invoke `/agent` and tools.

**Mitigation (operator):** Bind to localhost, firewall rules, reverse proxy with auth, or VPN.

## Tool surface

### `run_shell_command`

**Design:** Fixed allowlist of argv vectors only. No free-form shell.

**Residual risk:** Even read-only diagnostics leak system information to whoever controls prompts (the user in trusted deployment; an attacker if API is exposed).

### `fetch_url`

**Risk:** SSRF if API host can reach internal URLs.

**Mitigation (fork-level):** Add URL blocklists, allowlists, or network egress controls.

### `web_search`

**Risk:** Query content sent to SearXNG instance; egress per SearXNG config.

### `skye_infer` / Skye escalation

**Risk:** Prompt and context sent to remote host.

**Mitigation:** TLS, network segmentation, trust in remote Ollama admin.

### `send_discord_message`

**Risk:** Token exposure in `.env`; channel spam.

**Mitigation:** Least-privilege bot, secret storage, rate limits (not implemented in baseline).

## Data protection

- **At rest:** No application-level encryption; rely on disk encryption (BitLocker, etc.).
- **In transit:** HTTP by default between UI and API; **shall** use HTTPS in untrusted networks via external TLS termination.

## Logging

**Current state:** Standard logging to console; no structured redaction.

**Guidance:** Do not log full Discord tokens or user secrets when extending code.

## Dependency risk

Third-party packages (FastAPI, Chroma, httpx, etc.) carry supply-chain risk. Pin versions in production deployments.

## Related

- `reference/tools-catalog.md` — surface enumeration.
- `user/06-integrations.md` — operator setup.
