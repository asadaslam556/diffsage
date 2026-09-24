---
name: diffsage-agent-loop
description: Rules for changing DiffSage's agent loop, tools, profiles and SSE streaming (backend/app/agent/runner.py, tools.py, profiles.py, services/agent/stream.py). Use before editing any of them, adding a tool or profile, or debugging odd model behaviour such as raw JSON in replies, empty answers, or repeated tool calls.
---

# The agent loop

`AgentRunner.run` (`backend/app/agent/runner.py`) streams a model turn, runs any tool calls, feeds the results back, and repeats, up to `agent.max_tool_rounds`. The final round gets no tools, so the model has to answer. It knows nothing about HTTP, databases or specific providers; keep it that way.

## Guards that exist because real small models needed them

Every one of these came from a live run with `qwen2.5-coder:3b`. Don't remove one without a replacement and a test.

| Model behaviour | Guard | Test |
| --- | --- | --- |
| Writes the tool call as a JSON block in the reply | Text that could still be a tool call (starts with `{` or a code fence, under 2,000 chars) is held back and run as a real call if it parses. Prose is never delayed. | `test_tool_call_written_as_text_is_run_instead_of_shown` |
| Repeats the same call with the same arguments | Not re-run; the model is told it has the result, and tools are withdrawn | `test_repeating_the_same_tool_call_moves_the_model_on_to_the_answer` |
| Calls a tool it wasn't offered (the prompt mentions it) | "Withheld" tools answer "nothing to look up", then the model must answer | `test_a_withheld_tool_called_as_text_gets_a_clean_answer_not_raw_json` |
| Echoes the JSON schema as an argument value | `_int_arg` falls back to defaults; a bad `query` raises and shows as a failed lookup | `test_tool_arguments_that_echo_the_schema_fall_back_to_defaults` |
| Says nothing once tools are taken away | One-line `ANSWER_NOW` nudge; if still empty, the stream sends `empty_answer` and doesn't bill | `test_an_empty_answer_is_an_error_not_a_silent_success` |

Tools are only offered when there's data behind them (`tools_with_data` in `services/business/repository.py`). On a CPU every wasted round costs a minute or more.

## Adding a tool

1. Write the handler in `tools.py`. It gets a `ToolContext` and returns a string. **Raise** on bad input or failure; don't return an error string, or the UI shows the lookup as a success.
2. Tools reach data only through the gateway (`ctx.gateway.get`) with the 5-minute agent token. Add the exact method and path to `AGENT_ALLOWED` in `gateway/routes.py`, and keep it read-only.
3. Add the spec to `TOOLS`, list it in the profiles that should have it, and add a data check to `tools_with_data` if it can come back empty.
4. Mention it in the profile prompt as "if you have X", never unconditionally.
5. Tests: a happy-path run through `FakeGateway`, plus a malformed-argument case.

## Adding a profile (a new use case)

Add an `AgentProfile` in `profiles.py` with a system prompt and its tools. No runner, router or API changes are needed. The frontend picks profiles up from `/api/agent/profiles`.

## Streaming contract (`services/agent/stream.py`)

Events in order: `meta`, optional `fallback`, `provider`, `tool_start` / `tool_end`, many `token`, then exactly one of `done` or `error`. The frontend (`src/pages/Chat.jsx`) relies on this order.

- All refusals (402/403/422) happen in the router **before** the stream opens.
- `_persist` runs in an `anyio`-shielded `finally`: it always writes a reply row (empty if cancelled before any text) and a usage record. `BILLABLE` in `services/billing/service.py` decides what counts against quota.
- A provider failing *after* text has streamed is `stream_interrupted`; the router never splices a second model's answer onto the first.

## Checks before finishing

```powershell
cd backend
.venv\Scripts\python -m pytest -q tests/test_agent_runner.py tests/test_api.py tests/test_provider_router.py
.venv\Scripts\ruff check app tests
```
