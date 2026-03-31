# Developer Guide 05 — Agent Loop and Prompts

## Objective

Document the agent’s decision contract and prompt assembly. Changes here alter system behavior globally.

## Entry point

**Function:** `hexnode.agent.loop.run_agent`

**Parameters:**

- `user_message` — natural language task.
- `memory` — `MemoryStore` instance.
- `ollama` — `OllamaClient` instance.
- `interface` — string label stored in chat metadata (e.g. `api`, `desktop`, `discord`).

**Returns:** dict with `answer`, `confidence`, `steps`, `trace_id`, `escalated_skye`.

## Step budget

Maximum iterations = `settings.agent_max_steps` (default 4). Each iteration performs one `ollama.chat` call with `format_json=True`.

## Message stack

1. System message from `build_system_prompt(tool_specs, current_focus)`.
2. User message (original request).
3. Alternating assistant raw JSON and user “Observation:” messages after tool runs.
4. Nudge messages when the model omits action and answer per loop logic.

## Expected JSON shape (per step)

The prompt instructs the model to emit:

```json
{
  "thought": "string",
  "action": "tool_name or null",
  "action_input": { },
  "answer": "string or null",
  "confidence": 0.0
}
```

**Parsing:** `OllamaClient.parse_json_loose` tolerates surrounding prose by substring extraction.

**Fallback:** If parse fails, a synthetic object treats raw text as answer with low confidence.

## Termination conditions

- Model returns `action` null and non-empty `answer` with `confidence >= confidence_threshold` (default 0.75): stop after recording step.
- Model returns `action` null and `answer` with lower confidence: nudge for refinement (see source).
- Step limit reached: set fallback answer string if empty.

## Skye escalation

After the loop, if `confidence < confidence_threshold` and `skye_url` is set, perform HTTP generate to remote Ollama with a composed prompt (`skye_escalation_prompt`). On HTTP 200, replace or augment answer; bump confidence floor to 0.55.

## Persistence side effect

Every completed `run_agent` **shall** append one document to `chat_history` containing user line and Paradox answer, with metadata including `interface`, `trace_id`, `skye` flag.

## Prompt files

- `hexnode/agent/prompts.py` — `build_system_prompt`, `skye_escalation_prompt`, `format_observation`.

## Modification guidelines

- **Shall** keep JSON instructions and tool list synchronized with registry.
- **Shall not** increase step budget without assessing latency and cost.
- **May** add structured logging per `trace_id` for observability.

## HTTP surface (`POST /agent`)

The FastAPI route wraps `run_agent`. **`httpx.ReadTimeout`** from Ollama **shall** be translated to **504** so clients see a timeout message instead of an unhandled 500. See `hexnode/api/main.py` and `reference/rest-api.md`.

## Related

- `reference/agent-contract.md` — formal contract summary.
- `developer/03-architecture.md` — call graph.
