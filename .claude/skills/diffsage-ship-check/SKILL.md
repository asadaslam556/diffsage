---
name: diffsage-ship-check
description: Pre-ship verification for DiffSage. Use before saying a change is done, before committing or opening a PR, and before building the release zip. Runs tests, lint, build, compose validation, encoding and secret checks, and a docs check.
---

# Ship check

Run these from the repo root and show the output; don't claim "done" without it.

## 1. Tests, lint, build

```powershell
cd backend;  .venv\Scripts\python -m pytest -q;  .venv\Scripts\ruff check app tests;  cd ..
cd frontend; npm test; npm run build;  cd ..
docker compose config -q
```

If `backend\.venv` is missing: `.\diffsage.ps1 deps`. The backend tests need no services (SQLite, in-memory fakes, scripted models).

## 2. Nothing secret leaves the machine

- `.env` is git-ignored and must never be committed, printed, or put in the zip.
- `git status --short` must not list `.env`, `*.db`, `node_modules`, `.venv` or `.playwright-mcp`.
- If you put a fake provider key in `.env` for a fallback test, remove it: `Select-String -Path .env -Pattern deliberately` should find nothing.

## 3. Every text file is UTF-8

Windows Python writes cp1252 unless told otherwise, which once broke `App.jsx`.

```powershell
python .claude/skills/diffsage-ship-check/check_utf8.py
```

When writing files from Python yourself, always pass `encoding="utf-8"` to `open()`.

## 4. Docs still match the code

- Test counts in `README.md`, `docs/windows-setup.md` and the badges in `docs/code-review-report.md`.
- New behaviour or settings: note them in the relevant doc (`architecture.md`, `windows-setup.md`, `design.md`).
- Mermaid diagrams render. GitHub shows an error box for a broken one, so check changed diagrams in the Mermaid live editor or a quick local render.

## 5. Live smoke test (for changes to the stack, agent or UI)

Follow the "Verifying a change end to end" steps in the `diffsage-run` skill: health `ok`, sign in, a review streams, Stop works.

## 6. Packaging the zip

Zip the repo folder, excluding `node_modules`, `.venv`, `dist`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.git`, `.playwright-mcp` and **`.env`**. Afterwards, confirm that neither `.env` nor the value of `JWT_SECRET` appears inside the archive.
