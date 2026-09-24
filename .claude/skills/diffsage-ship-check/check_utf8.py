"""Fail if any text file in the repo isn't valid UTF-8.

Python on Windows writes cp1252 unless told otherwise, and one stray byte
(a "…" in App.jsx, once) breaks the frontend build output. Run from the repo root:

    python .claude/skills/diffsage-ship-check/check_utf8.py
"""

import pathlib
import sys

SKIP_DIRS = {"node_modules", ".venv", ".git", "dist", "__pycache__", ".pytest_cache", ".ruff_cache", ".playwright-mcp"}
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".woff", ".woff2", ".db"}

bad = []
for path in pathlib.Path(".").rglob("*"):
    if not path.is_file() or SKIP_DIRS & set(path.parts) or path.suffix.lower() in BINARY:
        continue
    try:
        path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        bad.append(f"{path} (byte {exc.start})")

if bad:
    print("Not UTF-8:\n  " + "\n  ".join(bad))
    sys.exit(1)
print("all text files are UTF-8")
