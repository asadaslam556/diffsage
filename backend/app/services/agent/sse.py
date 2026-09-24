import json
from typing import Any


def sse(event: str, data: dict[str, Any]) -> str:
    # one event per call; JSON never contains a raw newline so one data: line is enough
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
