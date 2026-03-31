# Developer Guide 04 — Tools and Registry

## Objective

Specify how tools are discovered, invoked, and validated.

## Base types

**File:** `hexnode/tools/base.py`

- `ToolContext` — fields: `memory`, `ollama`, `settings`, `trace_id`.
- `ToolResult` — fields: `ok`, `data`, `error`, `meta`.
- `Tool` — abstract shape: `name`, `description`, `async run(self, ctx, **params)`.

## Registry

**File:** `hexnode/tools/registry.py`

**Discovery algorithm:**

1. `pkgutil.iter_modules` over `hexnode.tools` package path.
2. Skip names starting with `_` and skip `base`, `registry`.
3. Import `hexnode.tools.<name>`.
4. For each class defined **in that module** (`__module__` match), if subclass of `Tool` and not `Tool` itself, instantiate.
5. If instance has truthy `name`, register.

**Invocation:**

- `registry.run(name, ctx, params_dict)` filters `params_dict` to keys accepted by `run` (excluding `self`, `ctx`). Unexpected keys are dropped silently.

## Adding a tool

1. Create `hexnode/tools/my_tool.py`.
2. Implement:

   ```python
   class MyTool(Tool):
       name = "my_tool"
       description = "One-line contract for the model."

       async def run(self, ctx: ToolContext, foo: str = "", **_: Any) -> ToolResult:
           ...
   ```

3. **Shall:** Keep `description` accurate; the LLM selects tools from this text.
4. Restart API (or rely on reload) and verify `GET /tools`.

## Error handling

Tools **should** return `ToolResult(ok=False, error="...")` rather than raise, except for unrecoverable programmer errors.

## Testing

Manual: `POST /agent` with a message that forces tool use.

Automated: **may** add pytest with mocked `OllamaClient` and in-memory Chroma; not present in baseline.

## Related

- `reference/tools-catalog.md` — operator-facing catalog.
- `reference/security.md` — shell and network tools.
