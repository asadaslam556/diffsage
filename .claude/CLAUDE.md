# DiffSage

Self-hosted AI code review SaaS. React 19 + Vite frontend, FastAPI backend, Postgres + Redis + Qdrant, Ollama by default with Claude / OpenAI / DeepSeek as optional providers. Follows the GenAI SaaS flow: user request → API gateway → (business API · agent service · billing) → data & storage → streamed UI response, with the agent calling back into the gateway for tool lookups.

Primary dev machine is **Windows** (PowerShell, Docker Desktop, CPU only). `make` is not available there; use `diffsage.ps1`.

## Commands

| Task | Windows | macOS / Linux |
| --- | --- | --- |
| Start everything in Docker | `.\diffsage.ps1 up` | `make up` |
| Health report | `.\diffsage.ps1 health` | `curl localhost:8000/api/health` |
| Backend logs | `.\diffsage.ps1 logs` | `make logs` |
| Stop | `.\diffsage.ps1 down` | `make down` |
| Install local deps | `.\diffsage.ps1 deps` | `make deps` |
| Backend + frontend tests | `.\diffsage.ps1 test` | `make test` |
| Lint | `.\diffsage.ps1 lint` | `make lint` |
| Only the data stores (for host dev) | `.\diffsage.ps1 infra` | `make infra` |

Single test: `backend\.venv\Scripts\python -m pytest tests/test_agent_runner.py -q` (from `backend/`). Frontend: `npm test` / `npm run build` in `frontend/`.

Ports come from `.env`: `WEB_PORT` (default 8080) and `API_PORT` (default 8000). On this machine they are **8088** and **8001** because 8080 is taken by a Windows service and 8000 by another local project. Always read them from `.env` rather than assuming the defaults.

## Where things live

```
backend/app/gateway/            route table, JWT check, agent-token scope, rate limits (pure ASGI)
backend/app/services/business/  auth, users, sessions, documents
backend/app/services/agent/     /api/agent/chat, SSE stream, persistence of replies + usage
backend/app/services/billing/   plans (code is the source of truth), quota checks, usage history
backend/app/services/health/    real checks for DB, Redis, Qdrant and every provider
backend/app/agent/              runner (agent loop), tools, profiles
backend/app/agent/providers/    one adapter per model API, registry, fallback router, _wire.py parsers
backend/config/settings.toml    non-secret defaults; override any key with SECTION__KEY env vars
frontend/src/pages/             Login, Dashboard, Chat, Settings
frontend/src/components/        HeroScene (three.js), TiltCard, Markdown (severity gutter), UsageChart
docs/                           architecture, windows-setup, adding-a-provider, design, code-review-report
```

## Rules that matter here

- **Never read, print, commit or zip `.env`.** It holds the JWT secret and any provider keys. Secrets come only from the environment; `settings.toml` holds non-secret defaults.
- **Write files as UTF-8.** Python on Windows defaults to cp1252; always pass `encoding="utf-8"` to `open()`. A cp1252 "…" once broke `App.jsx`.
- **Anything rejectable is rejected before the SSE stream opens** (402 quota, 403 plan, 422 input). Don't move checks into the stream.
- **Stream bookkeeping lives in the shielded `finally`** in `services/agent/stream.py`. Every run leaves a reply row (even empty on cancel) and a usage record. Empty answers are errors and aren't billed.
- **The last provider in the fallback chain is never cut off by the first-token timeout.** On CPU a cold model load takes minutes.
- **The agent loop is built for small local models.** See the `diffsage-agent-loop` skill before touching `runner.py` or `tools.py`.
- **Agent tokens may only call** `GET /api/app/documents/search` and `GET /api/app/reviews/recent`. Adding a tool that needs another route means adding it to `AGENT_ALLOWED` in `gateway/routes.py` on purpose.
- **UI follows `docs/design.md`**: one accent, sentence case, few 3D moments. See the `diffsage-ui` skill.
- Local inference on this laptop runs at about 1–3 tokens/s. A live review takes minutes; that's the hardware, not a hang.

## Project skills (`.claude/skills/`)

| Skill | Use it when |
| --- | --- |
| `diffsage-run` | starting, stopping, checking health, or debugging the running stack |
| `diffsage-agent-loop` | changing the agent runner, tools, profiles, or streaming |
| `diffsage-add-provider` | adding or changing a model provider |
| `diffsage-ui` | any frontend or visual change |
| `diffsage-ship-check` | before saying work is done, committing, or packaging |
