from __future__ import annotations

import os

import uvicorn


def _as_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=str(os.getenv("GPT_TOOLS_BACKEND_HOST") or "127.0.0.1").strip(),
        port=int(os.getenv("GPT_TOOLS_BACKEND_PORT") or "18777"),
        reload=_as_bool(os.getenv("GPT_TOOLS_BACKEND_RELOAD")),
    )
