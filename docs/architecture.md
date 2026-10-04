<p align="center"><img src="assets/logo.svg" alt="DiffSage" width="260" /></p>

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-pure%20ASGI%20gateway-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white" alt="Redis" />
  <img src="https://img.shields.io/badge/Qdrant-1.12.4-DC244C?logo=qdrant&logoColor=white" alt="Qdrant" />
  <img src="https://img.shields.io/badge/Ollama-0.34.3-000000?logo=ollama&logoColor=white" alt="Ollama" />
  <img src="https://img.shields.io/badge/Claude-Anthropic-D97757?logo=anthropic&logoColor=white" alt="Claude" />
  <img src="https://img.shields.io/badge/SSE-streaming-5fd4bf" alt="Server-Sent Events" />
</p>

# Architecture

How DiffSage is put together: the layers, every main flow, the data model, the API, configuration, deployment and the UI system. Paths are relative to `backend/app/` unless they say otherwise.

- [System and layers](#system-and-layers)
- [Gateway](#gateway)
- [One review, end to end](#one-review-end-to-end)
- [The agent loop](#the-agent-loop)
- [Providers and fallback](#providers-and-fallback)
- [Adding a provider](#adding-a-provider)
- [Guidelines (RAG)](#guidelines-rag)
- [Plans, quotas and usage](#plans-quotas-and-usage)
- [Auth](#auth)
- [Data model](#data-model)
- [Health](#health)
- [API reference](#api-reference)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [UI system](#ui-system)
- [Tests and CI](#tests-and-ci)

## System and layers

<p align="center"><img src="images/system.svg" alt="System overview" /></p>

A request from the browser goes through nginx to the gateway, which checks the route, the token and the rate limit. Then one of three services handles it, reading and writing the data stores, and the answer streams back. The agent calls back into the same gateway, with a short-lived token, when it needs to look something up.

| Layer | Package | Talks to | Never talks to |
| --- | --- | --- | --- |
| Web client | `frontend/src` | nginx `/api` only | anything else |
| Gateway | `gateway/` | Redis (rate limits), the routers | the database |
| Business API | `services/business/` | Postgres, Qdrant, the embedder | model providers |
| Agent service | `services/agent/`, `agent/` | provider router, the gateway (for tools), Postgres | Qdrant directly (tools go through the gateway) |
| Billing | `services/billing/` | Postgres, Redis | model providers |
| Health | `services/health/` | every store and provider, read-only | user data |

### Why a modular monolith

The services are separate FastAPI routers, with their own modules and no imports between each other's internals. They run in one process behind one gateway. For a product this size, that keeps them separate without network hops, extra deployments, or distributed tracing to debug a login. The gateway's route table (`gateway/routes.py`) is the only place that knows which prefix belongs to which service. Splitting one out later means pointing its prefix at another host.

### Start-up

`main.py` builds one container (`container.py`) in this order: database engine → session maker → plans synced from code → Redis (shared by the cache and the rate limiter) → providers (auto-discovered) → provider router → Qdrant store (made ready lazily) → embedder. Shutdown closes them in reverse. Middleware runs outermost first: server errors → CORS → request context (request ID, access log, security headers) → gateway → exception mapping → routers. The interactive `/docs` and `/openapi.json` are turned off in production.

## Gateway

<p align="center"><img src="images/gateway.svg" alt="Gateway request workflow" /></p>

The gateway (`gateway/middleware.py`) is plain ASGI middleware, so it never buffers a streaming response. For every `/api` request it:

1. **Matches the route table** by longest prefix. An unknown path is a `404 no_route` here, before any service runs.
2. **Checks the JWT** on non-public routes: `401 missing_token`, `token_expired` or `invalid_token`.
3. **Fences agent tokens.** A token with `scope=agent` may only call the two read-only routes in `AGENT_ALLOWED`; anything else is `403 agent_scope`.
4. **Counts the request** in a fixed window in Redis (`INCR` + `EXPIRE` in one transaction), keyed per user or per IP. Over the limit is `429 rate_limited` with `Retry-After`; every answer carries `X-RateLimit-*` headers. If Redis is down it lets traffic through and logs it (`rate_limits.fail_open`).

| Prefix | Service | Public | Rate bucket |
| --- | --- | --- | --- |
| `/api/health` | health | yes | default |
| `/api/auth` | business (auth) | yes | auth |
| `/api/app` | business | no | default |
| `/api/agent` | agent | no | agent |
| `/api/billing` | billing | no | default |

| Bucket | Limit |
| --- | --- |
| `auth` | 10 per minute per IP (sign-up, sign-in, refresh, sign-out) |
| `login_account` | 10 sign-in attempts per 15 minutes per account, whatever the IP |
| `agent` | 20 per minute per user |
| `default` | 120 per minute per user |

**Client IP.** nginx overwrites `X-Forwarded-For` with `$remote_addr` instead of appending to it, the gateway reads the rightmost hop, and the API port is published on `127.0.0.1` only. Together these stop a client from rotating a fake header to get around the per-IP limits.

**Errors** always have the same shape: `{"error": {"code", "message", "request_id"}}`. Every response carries an `X-Request-ID` (a valid incoming one is reused).

## One review, end to end

<p align="center"><img src="images/review-flow.svg" alt="Sequence of one review from the browser to the model and back" /></p>

Everything that can be rejected is rejected **before** the stream opens, so the browser gets a normal status code instead of a broken stream. `POST /api/agent/chat` runs these steps in order:

1. `422 empty_message` if there's nothing to review.
2. Resolve the provider against the plan: `403 provider_not_in_plan`.
3. Check the quota: `422 input_too_large`, then `402 daily_limit_reached` (with `Retry-After`), then `402 monthly_tokens_reached`.
4. Load or create the conversation (`404 session_not_found`). New conversations are titled from the first line of the message.
5. Check the profile (`422 unknown_profile`), load the last 20 messages, save the user message.
6. Mint a 5-minute agent token and decide which tools have data behind them.
7. Return the `StreamingResponse`.

### Stream events

The response is `text/event-stream` over a POST. The frontend reads it with `fetch` and a small parser (`frontend/src/api/sse.js`), because `EventSource` can't send a body or an `Authorization` header.

| Event | Data | When |
| --- | --- | --- |
| `meta` | `session_id`, `message_id`, `provider`, `profile` | always first |
| `provider` | `provider`, `model` | when a model starts answering |
| `fallback` | `from`, `to`, `reason` | a provider failed before its first token |
| `tool_start` / `tool_end` | `id`, `name`, args / `ok`, preview | the agent looked something up |
| `token` | `text` | every chunk of the answer |
| `error` | `code`, `message` | `providers_unavailable`, `stream_interrupted`, `empty_answer`, `internal_error`; ends the stream |
| `done` | `provider`, `model`, `input_tokens`, `output_tokens`, `latency_ms`, `status` | the answer finished |

nginx has `proxy_buffering off` for `/api/`, and responses carry `X-Accel-Buffering: no` in case another proxy sits in front. The **Stop** button aborts the fetch; the server sees the disconnect, cancels the provider call and records the run as `cancelled`.

### Bookkeeping

<p align="center"><img src="images/reply-status.svg" alt="Lifecycle of a reply's status: ok, fallback, error, cancelled" /></p>

The stream's `finally` block (`services/agent/stream.py`) is shielded and has its own database session and a 10-second budget. Every run leaves an assistant message and a usage record, whether it finished, failed, or the user closed the tab. An empty answer is an error, not a silent success. `ok`, `fallback` and `cancelled` runs are billed; `error` runs are recorded but not billed. When a provider doesn't report token counts, they are estimated at four characters per token.

## The agent loop

<p align="center"><img src="images/agent-loop.svg" alt="Agent loop: offer tools, stream a turn, run tool calls, answer" /></p>

`agent/runner.py` streams a turn from the provider router. If the model asks for a tool, it runs it through the gateway and goes round again, up to `max_tool_rounds` (3). The last round offers no tools, so the model has to answer.

| Tool | Calls | Offered when |
| --- | --- | --- |
| `search_guidelines(query, top_k)` | `GET /api/app/documents/search` | the user has uploaded guidelines |
| `get_past_reviews(limit)` | `GET /api/app/reviews/recent` | there are replies in another conversation |

Three profiles share the loop (`agent/profiles.py`): `code_reviewer` (default, both tools), `research_assistant` and `support_bot` (guidelines only).

### Built for small local models

Every guard below came from watching `qwen2.5-coder:3b` misbehave in a live run:

| What small models do | What the runner does |
| --- | --- |
| Write the tool call as JSON in the reply instead of the tool-call field | Holds back text that could still be a tool call (starts with `{` or a code fence) and runs it as a real call if it parses. Prose is never delayed. |
| Call the same tool with the same arguments over and over | Doesn't re-run it; says it already has the result and withdraws the tools. |
| Call a tool that wasn't offered | Answers "nothing to look up" and moves on to the answer. |
| Echo the JSON schema as an argument value | Arguments fall back to defaults instead of crashing. |
| Say nothing once the tools are gone | Adds a one-line "write your answer now" nudge. Still empty means an `empty_answer` error, which isn't billed. |

Tools are only offered when there's data behind them. On a CPU every extra round costs a minute or more.

## Providers and fallback

<p align="center"><img src="images/providers.svg" alt="Provider classes: Ollama, Anthropic, OpenAI-compatible, OpenAI, DeepSeek, behind one interface" /></p>

The router and the agent loop only ever see `LLMProvider` (`agent/providers/base.py`). Each adapter turns one vendor's wire format into the same stream of events.

| Provider | Adapter | Endpoint | Default model | Notes |
| --- | --- | --- | --- | --- |
| `ollama` | `ollama` | `POST /api/chat` (NDJSON) | `qwen2.5-coder:7b` | no key; embeddings via `/api/embed`; 600 s timeout |
| `anthropic` | `anthropic` | `POST /v1/messages` (SSE) | `claude-sonnet-5` | no temperature sent; works with gateways that speak the same API |
| `openai` | `openai_compatible` | `POST /chat/completions` (SSE) | `gpt-4o-mini` | any OpenAI-compatible host |
| `deepseek` | `openai_compatible` | `POST /chat/completions` (SSE) | `deepseek-flash` | tools off for `reasoner` models |

<p align="center"><img src="images/fallback.svg" alt="Fallback lifecycle: preferred, fallback, streaming, done, failed, interrupted" /></p>

The router (`agent/providers/router.py`) builds a chain: the user's preferred provider (or the server default), then `agent.fallback_provider` in order, skipping duplicates and anything the user's plan doesn't include. For each provider in turn:

- An error, a missing key, or no first event within **25 s** moves to the next one and emits a `fallback` event.
- **The last provider in the chain is never cut off by the first-token timeout.** It has nobody to hand over to, and a cold 7B model on a CPU-only laptop can need minutes just to load. It still has its own request timeout.
- A failure **after** text has streamed ends with `stream_interrupted`. A second model's answer is never spliced onto the first.

## Adding a provider

### It speaks the OpenAI chat completions API

Most do (Groq, Together, Mistral, OpenRouter, vLLM, LM Studio). No code needed; add a table to `backend/config/settings.toml`:

```toml
[providers.groq]
adapter = "openai_compatible"
base_url = "https://api.groq.com/openai/v1"
model = "llama-3.3-70b-versatile"
```

Set `GROQ_API_KEY` in `.env` and restart. The table name is what users see in Settings and what `AGENT__DEFAULT_PROVIDER` refers to, and it shows up in `/api/health` straight away.

### It has its own API

Add one file to `backend/app/agent/providers/`. Modules there are imported automatically, except ones starting with `_`.

```python
from app.agent.providers._http import raise_for_status, iter_sse_data, timed_get, health_from_response, wrap_transport_error
from app.agent.providers.base import LLMProvider, ProviderError, ProviderHealth
from app.agent.providers.registry import register_provider
from app.agent.types import StreamEvent


@register_provider("acme")
class AcmeProvider(LLMProvider):
    async def stream_response(self, messages, *, system=None, tools=None, temperature=0.2):
        body = {"model": self.model, "input": [m.content for m in messages], "stream": True}
        try:
            async with self.client.stream("POST", f"{self.config.base_url}/generate", json=body,
                                          headers={"authorization": f"Bearer {self.config.api_key}"}) as response:
                await raise_for_status(response, self.name)
                async for chunk in iter_sse_data(response):
                    if text := chunk.get("delta"):
                        yield StreamEvent.text_chunk(text)
                    if usage := chunk.get("usage"):
                        yield StreamEvent.usage_report(usage["in"], usage["out"])
        except ProviderError:
            raise
        except Exception as exc:
            raise wrap_transport_error(self.name, exc) from exc

    async def health_check(self) -> ProviderHealth:
        response, latency, error = await timed_get(self.client, f"{self.config.base_url}/models")
        return health_from_response(response, latency, error)
```

Then add `[providers.acme]` to `settings.toml` and set `ACME_API_KEY`. The rules that matter:

- **Raise `ProviderError` for anything that went wrong.** Never yield an error as text; the router needs the exception to decide whether to fall back.
- **Yield text as it arrives**, and tool calls only once their arguments are complete. `_wire.py` has parsers that buffer partial tool-call JSON.
- **`health_check` must not spend tokens.** Hit a model list or similar.
- **Set `requires_api_key = False`** for local servers, and `supports_tools = False` if the API can't do function calling.
- **Pure parsing goes in `_wire.py`**, so it can be tested without HTTP (see `tests/test_wire.py` and `tests/test_provider_adapters.py`).

## Guidelines (RAG)

<p align="center"><img src="images/guidelines.svg" alt="Guideline upload and search data flow through the embedder and Qdrant" /></p>

**Upload** (`POST /api/app/documents`, up to 200,000 characters): the text is split into line-aware chunks of 900 characters with 150 overlap, each chunk is embedded by Ollama (`nomic-embed-text`, 768 dimensions), the document row is written, the vectors go to Qdrant with the `user_id` in their payload, and then the transaction commits. If Qdrant fails, the row is rolled back and the request answers `503`.

**Search** (`GET /api/app/documents/search`, called by the agent's tool): the query is embedded the same way and Qdrant returns the closest chunks, always filtered by `user_id`, so one user never sees another's guidelines.

The collection name includes the embedding backend and dimension (`guidelines_ollama_768`). Switching embedding models creates a new collection instead of corrupting the old one.

## Plans, quotas and usage

<p align="center"><img src="images/usage.svg" alt="Usage data flow: quota check before the stream, usage record after it" /></p>

Plans live in code (`services/billing/plans.py`) and are synced to the database at start-up.

| Plan | Price | Requests per day | Tokens per month | Models | Max input |
| --- | --- | --- | --- | --- | --- |
| Free | $0 | 25 | 300k | Ollama only | 12k characters |
| Pro | $19 | 500 | 5M | all, can switch | 60k characters |
| Team | $49 | unlimited | unlimited | all, can switch | 150k characters |

Days and months are UTC. The quota check reads a 60-second usage snapshot from Redis, and every new usage record clears it. The dashboard's 14-day chart and request history come from `GET /api/billing/usage`.

Plan changes (`POST /api/billing/plan`) are self-serve for local use. With `billing.allow_self_serve_plan_change` off they answer `501 billing_not_configured`, and the app refuses to start in production with it on.

## Auth

<p align="center"><img src="images/sign-in.svg" alt="Sign-in sequence: password check, access token, refresh cookie" /></p>

- **Passwords** use PBKDF2-HMAC-SHA256 with 600,000 iterations and a 16-byte salt. Hashes are upgraded on sign-in if the setting goes up. A failed sign-in takes the same time whether or not the email exists.
- **Access tokens** are HS256 JWTs that last 15 minutes. The frontend keeps them in memory only.
- **Refresh tokens** are random, stored as SHA-256 hashes, last 14 days, and travel in an `HttpOnly`, `SameSite=Lax` cookie scoped to `/api/auth` (`Secure` in production).
- **Agent tokens** carry `scope=agent`, last 5 minutes, and only reach the two tool routes.
- **Sign-in limits** are per IP (10 a minute) and per account (10 per 15 minutes), so a slow attack spread across many addresses still runs out.

<p align="center"><img src="images/refresh-token.svg" alt="Refresh token lifecycle: active, rotated, reused, revoked, expired" /></p>

Refresh tokens rotate on every use. Presenting an already-rotated token within 20 seconds (two tabs refreshing at once) just fails; presenting it later is treated as theft and revokes every session for that user. Signing out revokes the current token.

The frontend retries a request once after a `401` by refreshing, with a single refresh in flight at a time.

## Data model

<p align="center"><img src="images/data-model.svg" alt="Database tables and the Qdrant collection" /></p>

One Alembic migration (`backend/alembic/versions/0001_*`) creates every table. Deleting a user cascades to everything they own; a usage record keeps its row if its conversation is deleted.

| Store | What's in it |
| --- | --- |
| Postgres | plans, users, refresh tokens (hashed), conversations, messages, usage records, guideline metadata |
| Redis | rate-limit counters and 60-second usage snapshots. No persistence; 256 MB, least recently used out first. |
| Qdrant | guideline chunks and their vectors, filtered per user |

## Health

`GET /api/health` checks every component concurrently, each with a 4-second timeout: `SELECT 1` on Postgres, `PING` on Redis, listing collections on Qdrant, and a cheap call on each provider (a model list, never a completion). Provider results are cached for 30 seconds, so a load balancer polling every few seconds doesn't hit paid APIs. `GET /api/health/live` is the plain liveness check the container uses.

| Condition | Status |
| --- | --- |
| Database down, or no usable provider | `down` (503) |
| Anything else not working, including the first fallback | `degraded` (200) |
| Everything working | `ok` (200) |

Ollama reports `degraded` when it's running but the configured model hasn't been pulled, with the exact `ollama pull` command in the detail. Providers without a key show `not_configured` and aren't probed.

## API reference

All routes are under `/api`. Interactive docs are at `/docs` outside production.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/health`, `/health/live` | Full health report; liveness |
| `POST` | `/auth/register`, `/auth/login` | Create an account (`409 email_taken`); sign in. Both return an access token and set the refresh cookie |
| `POST` | `/auth/refresh`, `/auth/logout` | Rotate the refresh token; sign out (`204`) |
| `GET` `PATCH` | `/app/me` | The current user; set the preferred provider |
| `GET` `POST` | `/app/sessions` | List or create conversations |
| `GET` `PATCH` `DELETE` | `/app/sessions/{id}` | One conversation with its messages; rename; delete |
| `GET` `POST` | `/app/documents` | List or upload guidelines |
| `DELETE` | `/app/documents/{id}` | Remove a guideline and its vectors |
| `GET` | `/app/documents/search` | Search guidelines (agent tool) |
| `GET` | `/app/reviews/recent` | Recent reviews from other conversations (agent tool) |
| `GET` | `/app/stats` | Conversation and guideline counts for the dashboard |
| `POST` | `/agent/chat` | Run a review; answers with the event stream above |
| `GET` | `/agent/providers`, `/agent/profiles` | Providers with plan access and health; agent profiles |
| `GET` | `/billing/plans`, `/billing/me` | Plans; the user's plan and current usage |
| `GET` | `/billing/usage?days=14` | Daily totals and the latest requests |
| `POST` | `/billing/plan` | Switch plan (self-serve setups only) |

## Configuration

Settings load in this order, later ones winning: `.env` in the repo root → `backend/.env` → `backend/config/settings.toml` → environment variables named `SECTION__KEY`. Secrets (`JWT_SECRET`, `<PROVIDER>_API_KEY`, `DATABASE_URL`, `QDRANT_API_KEY`) only ever come from the environment.

| Section | Keys (defaults) |
| --- | --- |
| `[app]` | `environment` (development), `log_level` (INFO), `log_format` (text; json in containers), `cors_origins`, `trust_proxy_headers` (true behind the bundled nginx) |
| `[auth]` | `access_token_minutes` (15), `refresh_token_days` (14), `password_hash_iterations` (600000) |
| `[rate_limits]` | `auth`, `login_account`, `agent`, `default` (see [Gateway](#gateway)), `fail_open` (true) |
| `[agent]` | `default_provider` (ollama), `fallback_provider` (ollama; one name or a comma-separated list), `first_token_timeout_seconds` (25), `max_tool_rounds` (3), `history_messages` (20), `default_profile` (code_reviewer) |
| `[embeddings]` | `backend` (ollama), `model` (nomic-embed-text), `dim` (768) |
| `[vectorstore]` | `collection_prefix` (guidelines) |
| `[billing]` | `allow_self_serve_plan_change` |
| `[health]` | `provider_cache_seconds` (30), `check_timeout_seconds` (4) |
| `[providers.<name>]` | `adapter`, `base_url`, `model`, `enabled`, `timeout_seconds`, `max_tokens` |

The app refuses to start if a rate limit or a named provider is missing. With `APP_ENVIRONMENT=production` it also refuses a weak `JWT_SECRET`, the default database password, or self-serve plan changes.

## Deployment

<p align="center"><img src="images/deployment.svg" alt="Docker Compose deployment: frontend, backend, Postgres, Redis, Qdrant, Ollama, ollama-pull" /></p>

| Service | Image | Port on the host | Notes |
| --- | --- | --- | --- |
| `frontend` | built: `node:22-alpine` → `nginx:1.27-alpine` | `WEB_PORT` (8080) | the only port open beyond localhost |
| `backend` | built: `python:3.12-slim`, non-root user | `127.0.0.1:API_PORT` (8000) | runs `alembic upgrade head`, then uvicorn; health check on `/api/health/live` |
| `postgres` | `postgres:16-alpine` | none | `pgdata` volume |
| `redis` | `redis:7-alpine` | none | in memory only |
| `qdrant` | `qdrant/qdrant:v1.12.4` | none | `qdrant` volume; pinned, see below |
| `ollama` | `ollama/ollama:0.34.3` | `127.0.0.1:OLLAMA_PORT` (11434) | `ollama` volume; keeps the model loaded for 24 h |
| `ollama-pull` | same | none | pulls the chat and embedding models, warms the chat model, exits |

`docker-compose.dev.yml` publishes Postgres, Redis and Qdrant on `127.0.0.1` for running the code on the host:

<p align="center"><img src="images/dev-modes.svg" alt="Everything in Docker versus code on the host" /></p>

nginx (`frontend/nginx.conf`) serves the built app with a strict Content Security Policy (only the app's own scripts, styles, fonts and API, no frames), `X-Frame-Options: DENY`, `nosniff` and a referrer policy. `/assets/` is cached for a year, and `/api/` is proxied without buffering with a 660-second read timeout, longer than the Ollama provider's own. TLS is left to whatever sits in front.

**Qdrant stays on 1.12.4.** Newer versions can't open storage created by 1.12 directly; the data has to be upgraded one minor version at a time. Dependabot is told to skip it.

## UI system

![Sign-in](screenshots/sign-in.png)

Everything lives in one stylesheet, `frontend/src/styles.css`, with no CSS framework.

1. **The review is the loudest thing on screen.** Everything around it stays quiet, so the severity gutter and the diff view carry the page.
2. **One accent.** A desaturated sage (`#5fd4bf`) marks actions, focus and "you are here".
3. **Colour means something.** Green and red are for added and removed lines; amber and sky only mark `major` and `minor`.
4. **Few 3D moments:** the crystal on sign-in, the isometric usage chart, and a gentle tilt on the cards you choose from. Everything else stays still.
5. **Every screen has its states:** skeletons while loading, a next step when empty, a cause and a fix on error.

| Group | Values | Rule |
| --- | --- | --- |
| Surfaces | `--bg #070b12` → `--bg-raise #0b111b` → `--surface #0e1520` → `--surface-2 #141d2b` | One cool-navy family, lighter as things come forward |
| Text | `--ink #e7edf5`, `--muted #98a6b8`, `--faint #7d8ca3` | Every text colour passes WCAG AA on every surface it sits on |
| Meaning | `--accent #5fd4bf`, `--add #4ade80`, `--del #f87171`, `--warn #f5b84a`, `--info #7cc4f0` | Accent for actions, the rest only for diff and severity |
| Radius | 6 / 9 / 13 / 18 px | Tight on small parts, softer on containers |
| Motion | `--ease`, `--spring` | Transform and opacity only; everything stops under `prefers-reduced-motion` |

**Type.** Geist for the interface and Geist Mono only for code, diffs and model names. Both are bundled (`@fontsource-variable/geist`, `@fontsource-variable/geist-mono`), so nothing is fetched from a third party and the CSP stays strict. Sentence case everywhere.

| Component | Where | Notes |
| --- | --- | --- |
| Severity gutter and diff view | `components/Markdown.jsx` | `[blocker]` / `[major]` / `[minor]` / `[nit]` become a coloured gutter; `+` / `-` lines get washes. Builds elements, never `innerHTML`. |
| Crystal | `components/HeroScene.jsx` | three.js, lazy-loaded, pauses in hidden tabs, frees GPU memory on unmount |
| Tilt card | `components/TiltCard.jsx`, `lib/tilt.js` | Off on touch screens and under reduced motion |
| Isometric chart | `components/UsageChart.jsx` | Plain SVG, today's bar in the brighter accent |

**Accessibility.** A skip link and a visible focus ring; labels on icon-only buttons; inline form errors with `aria-invalid`; the streaming reply in an `aria-live` region; touch targets of at least 40 px and no horizontal scrolling at 390 px wide.

## Tests and CI

<img src="https://img.shields.io/badge/pytest-122%20passing-0A9EDC?logo=pytest&logoColor=white" alt="pytest" /> <img src="https://img.shields.io/badge/Vitest-9%20passing-6E9F18?logo=vitest&logoColor=white" alt="Vitest" /> <img src="https://img.shields.io/badge/GitHub%20Actions-CI-2088FF?logo=githubactions&logoColor=white" alt="GitHub Actions" />

The backend tests run the real app in-process with SQLite, in-memory stand-ins for Redis and Qdrant, and scripted fake models, so they need no services. CI (`.github/workflows/ci.yml`) has four jobs: backend lint and tests, migrations up / down / up on a real Postgres 16, frontend tests and build, and both Docker image builds. CodeQL scans every push, and Dependabot opens one grouped update PR per ecosystem each week.
