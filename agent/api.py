"""FastAPI application exposing the BlackRoad agent API."""

from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel
import uvicorn

from agent import telemetry, jobs
from agent.config import auth_token as get_auth_token
from agent.config import load as load_cfg
from agent.config import save as save_cfg

app = FastAPI(title="BlackRoad Agent API", version="1.0.0")

JETSON_HOST = os.getenv("JETSON_HOST", "jetson.local")
JETSON_USER = os.getenv("JETSON_USER", "jetson")
AUTH_TOKEN = os.getenv("AGENT_AUTH_TOKEN")

if not AUTH_TOKEN:
    raise RuntimeError("AGENT_AUTH_TOKEN environment variable must be set for the API service")


def require_bearer_token(authorization: str = Header(default="")):
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


class JobRequest(BaseModel):
    command: str


@app.get("/healthz")
def healthcheck() -> Dict[str, Any]:
    """Return a minimal health payload."""
    return {"ok": True, "auth": bool(get_auth_token())}


@app.get("/settings")
def read_settings() -> Dict[str, Any]:
    """Return the current configuration."""
    return load_cfg()


@app.post("/settings/auth")
def set_auth_token(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    """Persist a new shared authentication token."""
    token = (payload or {}).get("token", "")
    if token is None:
        token = ""
    token = str(token).strip()
    cfg = load_cfg()
    cfg.setdefault("auth", {})["token"] = token
    save_cfg(cfg)
    return {"ok": True, "enabled": bool(token)}


@app.get("/status")
def status(_: None = Depends(require_bearer_token)):
    return {
        "target": {"host": JETSON_HOST, "user": JETSON_USER},
        "pi": telemetry.collect_local(),
        "jetson": telemetry.collect_remote(JETSON_HOST, user=JETSON_USER),
    }


@app.post("/run")
def run_job(req: JobRequest, _: None = Depends(require_bearer_token)):
    jobs.run_remote(JETSON_HOST, req.command, user=JETSON_USER)
    return {"ok": True, "command": req.command}


def main():
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
