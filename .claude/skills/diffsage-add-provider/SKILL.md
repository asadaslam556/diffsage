---
name: diffsage-add-provider
description: Add or change a model provider in DiffSage (Ollama, Claude, OpenAI, DeepSeek, or any OpenAI-compatible API) through the pluggable adapter registry. Use when asked to support a new LLM API, change a default model, or debug provider errors, health or fallback.
---

# Model providers

Every provider implements `LLMProvider` (`backend/app/agent/providers/base.py`): `stream_response`, `health_check`, and optionally `embed`. `ProviderRouter` (`router.py`) picks the preferred provider and falls back to `agent.fallback_provider` (Ollama). Nothing above the provider layer ever sees a vendor's wire format.

## OpenAI-compatible API (Groq, Together, OpenRouter, vLLM, LM Studio...): config only

Add a table to `backend/config/settings.toml`:

```toml
[providers.groq]
adapter = "openai_compatible"
base_url = "https://api.groq.com/openai/v1"
model = "llama-3.3-70b-versatile"
```

Then put `GROQ_API_KEY=` in `.env` (the env var is `<TABLE NAME>_API_KEY`, so keep table names alphanumeric) and restart the backend. It appears in Settings and `/api/health` automatically.

## A new API: one file

Add `backend/app/agent/providers/<name>.py` with a class decorated `@register_provider("<name>")`. Modules in that package are auto-imported, except names starting with `_`. Follow `anthropic.py` or `ollama.py`:

- **Raise `ProviderError`** for anything that fails. Never yield an error as text; the router needs the exception to decide on fallback.
- **Yield text as it arrives**; yield tool calls only once their arguments are complete.
- **Put the pure parsing in `_wire.py`** so it can be tested with plain dicts (see `tests/test_wire.py`).
- **`health_check` must not spend tokens**: hit a model list or tags endpoint.
- Set `requires_api_key = False` for local servers, and `supports_tools = False` if the API can't do function calling.

Then add the `[providers.<name>]` table and a label in `frontend/src/lib/format.js` (`PROVIDER_LABELS`).

## Things that bite

- Anthropic rejects conversations that start with an assistant turn or an orphaned `tool_result`; `anthropic_messages` trims those. Keep that if you touch it.
- The last provider in the chain gets no first-token timeout; others get `agent.first_token_timeout_seconds`.
- Ollama's `timeout_seconds` is 600 on purpose (it's the last resort, and CPU prompt processing is slow).
- Plan rules decide who may pick a provider (`services/billing/plans.py`): Free is local-only.

## Test it

```powershell
cd backend
.venv\Scripts\python -m pytest -q tests/test_provider_adapters.py tests/test_provider_router.py tests/test_wire.py
```

Live: set a deliberately invalid key, restart the backend, and confirm health shows `API key rejected` and a review falls back to Ollama with a visible notice. Remove the fake key afterwards.
