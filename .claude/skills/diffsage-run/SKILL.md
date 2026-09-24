---
name: diffsage-run
description: Start, stop, health-check and troubleshoot the DiffSage stack (Docker Compose + Ollama) on Windows or Unix. Use when asked to run the app, check it's working, read logs, fix "ports are not available", slow or failing reviews, or a degraded health report.
---

# Running DiffSage

## Start and check

```powershell
.\diffsage.ps1 up       # builds, starts 7 containers, waits for /api/health/live, opens the browser
.\diffsage.ps1 health   # full component report (works even when the API returns 503)
```

Read the ports from `.env` (`WEB_PORT`, `API_PORT`, defaults 8080 / 8000). On the main dev machine they are 8088 / 8001. The app is at `http://localhost:<WEB_PORT>`, the API at `http://localhost:<API_PORT>`.

Containers: `postgres`, `redis`, `qdrant`, `ollama`, `ollama-pull` (pulls and warms the models, then exits), `backend`, `frontend` (nginx). The compose project name is `diffsage`, so volumes (database, downloaded models) survive a folder rename.

## Reading the health report

| Status | Meaning |
| --- | --- |
| `ok` | everything answered |
| `degraded` (200) | something non-essential is off: Redis, Qdrant, one provider, or Ollama running without its model pulled yet |
| `down` (503) | the database is down, or no model provider works at all |

Provider results are cached for 30 s, so after fixing something wait that long before re-checking.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `ports are not available` on 8080 or 8000 | Another program holds it. Check with `Get-NetTCPConnection -LocalPort 8000 -State Listen` and **don't kill processes you didn't start**. Set `WEB_PORT` / `API_PORT` in `.env` and run `up` again. |
| Ollama `degraded: model isn't pulled` | `ollama-pull` is still downloading: `docker compose logs -f ollama-pull`. |
| Reviews take minutes | CPU inference is ~1–3 tokens/s here. Use `OLLAMA_MODEL=qwen2.5-coder:3b`, a paid provider key, or an NVIDIA GPU (`deploy:` block in compose). |
| "None of the AI providers responded" | Check `health`. Usually Ollama isn't up or has no model; with a paid default, also check the key (`API key rejected`). |
| Guideline upload fails "Couldn't index the file" | `nomic-embed-text` not pulled yet. |
| API returns 503 `service_unavailable` | A backing service (usually Postgres) is unreachable. `docker compose ps`, then start it. The app recovers on its own. |
| Signed out after a backend restart | `JWT_SECRET` in `.env` is empty or a placeholder, so each process picks a random one. `.\diffsage.ps1 setup` writes a stable one. |

## Verifying a change end to end

1. `docker compose up -d --build backend frontend`.
2. Wait for `/api/health/live`, then check `health` is `ok`.
3. In the browser: sign in → Usage shows numbers → Reviews → click an example → the reply streams in chunk by chunk → Stop works.
4. For provider changes, put a deliberately invalid key in `.env`, restart the backend, and confirm the fallback notice appears. **Remove the fake key afterwards.**

Local model runs are slow; for anything that only needs to prove the plumbing, prefer the backend tests (they use scripted fake models).
