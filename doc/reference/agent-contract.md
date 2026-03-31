# Technical Reference — Agent Contract

## Objective

Formalize the agent loop’s inputs, outputs, and invariants independent of UI.

## Inputs

| Name | Source | Description |
|------|--------|-------------|
| User message | HTTP or script | Natural language task. |
| Tool catalog | Registry at runtime | Injected into system prompt. |
| Current focus | File `current_focus.md` | Injected into system prompt. |
| Models | `CHAT_MODEL`, `EMBED_MODEL` | Ollama identifiers. |
| Limits | `agent_max_steps`, `confidence_threshold` | Termination policy. |

## Per-step model output (normative intent)

The model **should** return JSON with keys:

- `thought` — reasoning string.
- `action` — tool name or JSON null.
- `action_input` — object of parameters or empty object.
- `answer` — final string or null while tooling.
- `confidence` — number in \([0,1]\).

**Parser behavior:** Best-effort JSON extraction; malformed output degrades to heuristic fallback.

## Tool invocation

When `action` is non-null:

1. Registry dispatches to tool `name`.
2. `ToolResult` is formatted as observation text and appended to the chat as a user-role message (see implementation).
3. Loop continues unless outer logic breaks (see source).

## Termination

**Satisfied answer path:** `action` null, `answer` present, `confidence >= confidence_threshold`.

**Unsatisfied path:** nudge messages until step limit.

**Post-loop:** If confidence below threshold and Skye configured, remote generate augments answer.

## Outputs

| Field | Semantics |
|-------|-----------|
| `answer` | User-visible string. |
| `confidence` | Reported confidence after Skye adjustment rules. |
| `steps` | Audit-friendly step list. |
| `trace_id` | Short id for correlation. |
| `escalated_skye` | Boolean flag. |

## Side effects

- Exactly one new `chat_history` document per `run_agent` call under normal completion.

## Extended response fields (HTTP)

The `/agent` handler **may** include:

- `symbolic_hints` — optional string of matched neuro-symbolic hints.
- `react_version` — e.g. `v2` when step records include `parse_ok` / `tool_ok`.

## HTTP errors (operator-facing)

When the upstream Ollama call exceeds the configured read timeout, the API returns **504** with a clear message (not a generic 500). Other client-visible status codes for `/agent` are documented in [REST API](rest-api.md).

## Versioning

Any change to JSON keys or stop conditions **shall** bump documentation and **should** bump application version (`VERSION`, `pyproject.toml`, Tauri config as applicable).

## Related

- `developer/05-agent-and-prompts.md` — implementation detail.
- `reference/rest-api.md` — HTTP mapping.
