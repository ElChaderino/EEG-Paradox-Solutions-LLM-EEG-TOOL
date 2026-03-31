# Developer Guide 07 — Neuro-Symbolic Rules

## Objective

Describe deterministic **regex → hint** routing that augments the LLM system prompt without invoking tools.

## Files

| Path | Role |
|------|------|
| `hexnode/symbolic/default_rules.yaml` | Shipped defaults; do not rely on `data/` existing. |
| `data/rules.yaml` | Optional operator extensions (merged after defaults). |
| `rules.example.yaml` | Repository template to copy to `data/rules.yaml`. |

## Schema

```yaml
version: 1
hints:
  - pattern: "(?i)regex"
    text: "One-line hint for the model when pattern matches user message."
```

Patterns use Python `re.search`. Invalid patterns are skipped silently.

## Runtime

`load_symbolic_hints(user_message, settings)` returns a markdown section appended to the system prompt in `build_system_prompt(..., symbolic_suffix=...)`. Disable with `SYMBOLIC_ENABLED=false`.

## Design constraints

- **Shall not** execute code or network calls.
- **Shall not** replace tool execution; hints only bias selection.
- **May** overlap; all matching hints are listed.

## Related

- `reference/configuration.md` — `SYMBOLIC_*` variables.
- `developer/05-agent-and-prompts.md` — prompt assembly.
