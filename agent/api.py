"""FastAPI application exposing the BlackRoad agent API.

This module provides a unified API surface for:
- Health checks and status monitoring
- Telemetry collection (local and remote)
- Job execution on remote hosts
- Device flashing capabilities
- Model inference endpoints
- Audio transcription
- WebSocket streaming for real-time updates
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import pathlib
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import (
    Body,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.websockets import WebSocketState

from agent import flash, jobs, models, telemetry, transcribe
from agent.auth import TokenAuthMiddleware
from agent.config import (
    DEFAULT_USER,
    active_target,
    auth_token as get_auth_token,
    load as load_cfg,
    save as save_cfg,
    set_target,
)

# Environment configuration
JETSON_HOST = os.getenv("JETSON_HOST", "jetson.local")
JETSON_USER = os.getenv("JETSON_USER", "jetson")
AUTH_TOKEN = os.getenv("AGENT_AUTH_TOKEN", "")

# FastAPI application
app = FastAPI(
    title="BlackRoad Agent API",
    version="1.0.0",
    description="Unified API for BlackRoad agent services",
    docs_url="/_docs",
    redoc_url="/_redoc",
)

# Add authentication middleware
app.add_middleware(TokenAuthMiddleware)

# Templates for dashboard
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Known OS images for flashing
KNOWN_IMAGES = [
    {
        "name": "Raspberry Pi OS Lite (arm64)",
        "url": "https://downloads.raspberrypi.com/raspios_lite_arm64_latest",
    },
    {
        "name": "Ubuntu Server 24.04 (RPI arm64)",
        "url": "https://cdimage.ubuntu.com/releases/24.04/release/ubuntu-24.04.1-preinstalled-server-arm64+raspi.img.xz",
    },
    {
        "name": "BlackRoad OS (latest)",
        "url": "https://releases.blackroad.io/os/latest.img.xz",
        "sha256": "https://releases.blackroad.io/os/latest.sha256",
    },
]


# ==============================================================================
# Request/Response Models
# ==============================================================================


class JobRequest(BaseModel):
    """Request model for job execution."""
    command: str
    host: Optional[str] = None
    user: Optional[str] = None


class JetsonSettings(BaseModel):
    """Settings for Jetson target configuration."""
    host: str
    user: str = "jetson"


# ==============================================================================
# Authentication Helpers
# ==============================================================================


def require_bearer_token(authorization: str = Header(default="")) -> None:
    """Validate bearer token authentication."""
    if not AUTH_TOKEN:
        return  # No token configured, allow all

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ==============================================================================
# WebSocket Connection Manager
# ==============================================================================


class ConnectionManager:
    """Minimal WebSocket manager for streaming logs."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, message: str) -> None:
        for ws in list(self._connections):
            try:
                await ws.send_text(message)
            except RuntimeError:
                self.disconnect(ws)


manager = ConnectionManager()


# ==============================================================================
# Health & Status Endpoints
# ==============================================================================


@app.get("/health")
@app.get("/healthz")
def healthcheck() -> Dict[str, Any]:
    """Return a minimal health payload for load balancers."""
    return {
        "ok": True,
        "service": "blackroad-agent",
        "auth_enabled": bool(get_auth_token()),
    }


@app.get("/status")
def get_status(_: None = Depends(require_bearer_token)) -> Dict[str, Any]:
    """Return comprehensive status with telemetry."""
    try:
        pi_telemetry = telemetry.collect_local()
    except Exception as exc:
        pi_telemetry = {"status": "error", "detail": str(exc)}

    try:
        jetson_telemetry = telemetry.collect_remote(JETSON_HOST, user=JETSON_USER)
    except Exception as exc:
        jetson_telemetry = {"status": "error", "detail": str(exc)}

    return {
        "ok": True,
        "target": {"host": JETSON_HOST, "user": JETSON_USER},
        "pi": pi_telemetry,
        "jetson": jetson_telemetry,
    }


# ==============================================================================
# Dashboard Endpoints
# ==============================================================================


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Serve the dashboard UI."""
    context: Dict[str, Any] = {
        "request": request,
        "target": active_target(),
    }
    try:
        return templates.TemplateResponse("dashboard.html", context)
    except Exception:
        return HTMLResponse("<h1>BlackRoad Agent</h1><p>Dashboard unavailable</p>")


# ==============================================================================
# Settings Endpoints
# ==============================================================================


@app.get("/settings")
def get_settings() -> Dict[str, Any]:
    """Return the active configuration."""
    host, user = active_target()
    return {
        "jetson": {"host": host, "user": user},
        "raw": load_cfg(),
    }


@app.post("/settings/auth")
def set_auth_token(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Persist a new shared authentication token."""
    token = (payload or {}).get("token", "")
    if token is None:
        token = ""
    token = str(token).strip()
    cfg = load_cfg()
    cfg.setdefault("auth", {})["token"] = token
    save_cfg(cfg)
    return {"ok": True, "enabled": bool(token)}


@app.post("/settings/jetson")
def set_jetson_settings(settings: JetsonSettings) -> Dict[str, Any]:
    """Update the Jetson target configuration."""
    if not settings.host:
        return {"ok": False, "error": "host required"}
    set_target(settings.host, settings.user)
    return {"ok": True, "jetson": {"host": settings.host, "user": settings.user}}


# ==============================================================================
# Discovery Endpoints
# ==============================================================================


@app.get("/discover/target")
def discover_target() -> Dict[str, Any]:
    """Get the current target configuration."""
    target = active_target()
    if not target:
        return {"ok": False, "jetson": None}
    return {"ok": True, "jetson": {"host": target[0], "user": target[1]}}


@app.get("/discover/scan")
def discover_scan() -> Dict[str, Any]:
    """Scan for available devices on the network."""
    from agent import discover
    return discover.scan()


@app.post("/discover/set")
def discover_set(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Set the target device for operations."""
    host = payload.get("host")
    user = payload.get("user", DEFAULT_USER)
    if not host:
        return {"ok": False, "error": "host required"}
    try:
        set_target(host, user)
        return {"ok": True, "target": {"host": host, "user": user}}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


# ==============================================================================
# Telemetry Endpoints
# ==============================================================================


@app.get("/telemetry/local")
def telemetry_local() -> Dict[str, Any]:
    """Expose local telemetry for the dashboard."""
    return telemetry.collect_local()


@app.get("/telemetry/remote")
def telemetry_remote(host: Optional[str] = None, user: Optional[str] = None) -> Dict[str, Any]:
    """Expose remote telemetry, allowing overrides via query parameters."""
    return telemetry.collect_remote(host=host, user=user)


@app.get("/connect/test")
def connect_test() -> Dict[str, Any]:
    """Attempt to gather telemetry from both Pi and Jetson."""
    try:
        pi = telemetry.collect_local()
        jetson = telemetry.collect_remote()
        ok = all(not str(value).startswith("error") for value in jetson.values())
        return {"ok": ok, "pi": pi, "jetson": jetson}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ==============================================================================
# Job Execution Endpoints
# ==============================================================================


@app.post("/run")
@app.post("/jobs/run")
def run_job(req: JobRequest, _: None = Depends(require_bearer_token)) -> Dict[str, Any]:
    """Execute a remote command on the target host."""
    if not req.command:
        return {"ok": False, "error": "command required"}

    try:
        result = jobs.run_remote(
            req.command,
            host=req.host or JETSON_HOST,
            user=req.user or JETSON_USER,
        )
        return {
            "ok": result.returncode == 0,
            "command": req.command,
            "stdout": (result.stdout or "").strip(),
            "stderr": (result.stderr or "").strip(),
            "returncode": result.returncode,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ==============================================================================
# SSH Key Management
# ==============================================================================


@app.post("/connect/install-key")
def install_ssh_key() -> Dict[str, Any]:
    """Generate SSH key and copy to target host."""
    host, user = active_target()
    home = pathlib.Path.home()
    ssh_dir = home / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    key_path = ssh_dir / "id_rsa"

    if not key_path.exists():
        subprocess.run(
            ["ssh-keygen", "-t", "rsa", "-N", "", "-f", str(key_path)],
            check=True,
        )

    result = subprocess.call(
        ["ssh-copy-id", "-i", f"{key_path}.pub", f"{user}@{host}"]
    )

    return {
        "ok": result == 0,
        "note": "If this failed, run ssh-copy-id manually to enter the password.",
    }


# ==============================================================================
# Flash Endpoints
# ==============================================================================


@app.get("/flash/devices")
async def flash_devices() -> Dict[str, Any]:
    """Return removable block devices available for flashing."""
    devices = await asyncio.to_thread(flash.list_devices)
    if isinstance(devices, dict) and "error" in devices:
        raise HTTPException(status_code=500, detail=devices.get("error"))
    return {"devices": devices}


@app.get("/flash/images")
def flash_images() -> Dict[str, Any]:
    """Return curated OS image suggestions."""
    return {"images": KNOWN_IMAGES}


@app.get("/flash/probe")
def flash_probe(host: Optional[str] = None, user: Optional[str] = None) -> Dict[str, Any]:
    """Probe flash capabilities on remote host."""
    return flash.probe(host=host, user=user)


def _start_flash_worker(
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    device: str,
    image_url: str,
    safe_hdmi: bool,
    enable_ssh: bool,
    stop: threading.Event,
) -> threading.Thread:
    """Start a background thread for flash operations."""
    def worker() -> None:
        try:
            for line in flash.flash(
                image_url,
                device,
                safe_hdmi=safe_hdmi,
                enable_ssh=enable_ssh,
            ):
                if stop.is_set():
                    break
                asyncio.run_coroutine_threadsafe(queue.put(line), loop)
        except Exception as exc:
            asyncio.run_coroutine_threadsafe(queue.put(f"ERROR: {exc}"), loop)
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    thread = threading.Thread(target=worker, name="flash-writer", daemon=True)
    thread.start()
    return thread


@app.websocket("/ws/flash")
async def ws_flash(ws: WebSocket) -> None:
    """Stream flashing progress via WebSocket."""
    await ws.accept()
    stop = threading.Event()
    queue: asyncio.Queue = asyncio.Queue()
    thread: Optional[threading.Thread] = None

    try:
        msg = await ws.receive_json()
        device = msg.get("device")
        image_url = msg.get("image_url")
        safe_hdmi = bool(msg.get("safe_hdmi", True))
        enable_ssh = bool(msg.get("enable_ssh", True))

        if not device or not image_url:
            await ws.send_text("ERROR: device and image_url are required")
            await ws.send_text("[[BLACKROAD_DONE]]")
            return

        loop = asyncio.get_running_loop()
        thread = _start_flash_worker(
            queue, loop, device, image_url, safe_hdmi, enable_ssh, stop
        )

        while True:
            line = await queue.get()
            if line is None:
                break
            await ws.send_text(line)

        await ws.send_text("[[BLACKROAD_DONE]]")
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await ws.send_text(f"ERROR: {exc}")
        await ws.send_text("[[BLACKROAD_DONE]]")
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=1)
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.close()


# ==============================================================================
# Model Endpoints
# ==============================================================================


@app.get("/models")
async def get_models() -> JSONResponse:
    """Return available local GGUF/BIN models."""
    return JSONResponse({"models": models.list_local_models()})


@app.post("/models/run")
def models_run(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Run a llama.cpp model with the provided prompt."""
    model = (payload or {}).get("model")
    prompt = (payload or {}).get("prompt", "")
    n_raw = (payload or {}).get("n", 128)

    if not model or not prompt:
        return {"error": "model and prompt required"}

    try:
        n_predict = max(1, int(n_raw))
    except (TypeError, ValueError):
        return {"error": "n must be an integer"}

    model_path = Path(model)
    if not model_path.exists():
        candidate = models.MODELS_DIR / model
        model_path = candidate if candidate.exists() else model_path

    try:
        resolved = model_path.resolve(strict=True)
    except FileNotFoundError:
        return {"error": f"model not found: {model}"}

    # Security check: ensure model is in allowed directory
    try:
        resolved.relative_to(models.MODELS_DIR.resolve())
    except ValueError:
        return {"error": "model must live under the models directory"}

    return models.run_llama(str(resolved), prompt, n_predict=n_predict)


@app.websocket("/ws/model")
async def ws_model(ws: WebSocket) -> None:
    """Stream llama.cpp output via WebSocket."""
    await ws.accept()
    try:
        message = await ws.receive_json()
        model = message.get("model")
        prompt = message.get("prompt", "")
        try:
            n_predict = int(message.get("n", 128))
        except (TypeError, ValueError):
            n_predict = 128

        if not model:
            await ws.send_text("[error] model path missing")
            await ws.send_text("[[BLACKROAD_MODEL_DONE]]")
            return

        loop = asyncio.get_running_loop()
        done_event = asyncio.Event()

        def stream_tokens() -> None:
            try:
                for token in models.run_llama_stream(model, prompt, n_predict=n_predict):
                    send_future = asyncio.run_coroutine_threadsafe(
                        ws.send_text(token), loop
                    )
                    try:
                        send_future.result()
                    except WebSocketDisconnect:
                        break
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(
                    ws.send_text(f"[error] {exc}"), loop
                ).result()
            finally:
                asyncio.run_coroutine_threadsafe(
                    ws.send_text("[[BLACKROAD_MODEL_DONE]]"), loop
                ).result()
                loop.call_soon_threadsafe(done_event.set)

        await asyncio.gather(asyncio.to_thread(stream_tokens), done_event.wait())
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await ws.send_text(f"[error] {exc}")
        await ws.send_text("[[BLACKROAD_MODEL_DONE]]")
    finally:
        with contextlib.suppress(RuntimeError):
            await ws.close()


# ==============================================================================
# Transcription Endpoints
# ==============================================================================


@app.post("/transcribe")
async def transcribe_audio_simple(file: UploadFile = File(...)) -> Dict[str, str]:
    """Accept an uploaded audio file and run whisper.cpp locally."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        data = await file.read()
        tmp.write(data)
        tmp_path = pathlib.Path(tmp.name)

    try:
        text = transcribe.run_whisper(str(tmp_path))
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"text": text}


@app.post("/transcribe/upload")
async def transcribe_upload(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Upload audio file for streaming transcription."""
    data = await file.read()
    suffix = pathlib.Path(file.filename or "audio.wav").suffix
    path = transcribe.save_upload(data, suffix=suffix)
    token = pathlib.Path(path).name
    return {"token": token}


@app.websocket("/ws/transcribe/run")
async def ws_transcribe(ws: WebSocket) -> None:
    """Stream transcription results via WebSocket."""
    await ws.accept()
    try:
        msg = await ws.receive_text()
        payload = json.loads(msg)
        token = payload.get("token")
        lang = payload.get("lang", "en")
        model = payload.get("model")

        if not token:
            await ws.send_text("[error] missing token")
            return

        candidate = (transcribe.TMP_DIR / token).resolve()
        try:
            candidate.relative_to(transcribe.TMP_DIR)
        except ValueError:
            await ws.send_text("[error] bad token")
            return

        if not candidate.exists():
            await ws.send_text("[error] audio not found")
            return

        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def pump_stream() -> None:
            try:
                for line in transcribe.run_whisper_stream(
                    str(candidate), model_path=model, lang=lang
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, ("data", line))
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

        thread = threading.Thread(target=pump_stream, name="whisper-stream", daemon=True)
        thread.start()

        try:
            while True:
                kind, data = await queue.get()
                if kind == "data" and data is not None:
                    await ws.send_text(data)
                elif kind == "error" and data is not None:
                    await ws.send_text(f"[error] {data}")
                elif kind == "done":
                    await ws.send_text("[[BLACKROAD_WHISPER_DONE]]")
                    break
        finally:
            if thread.is_alive():
                await asyncio.to_thread(thread.join)
    except WebSocketDisconnect:
        pass
    except json.JSONDecodeError:
        await ws.send_text("[error] invalid json")
    except Exception as exc:
        await ws.send_text(f"[error] {exc}")
    finally:
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await ws.close()


# ==============================================================================
# WebSocket Logs
# ==============================================================================


@app.websocket("/ws/logs")
async def logs_websocket(websocket: WebSocket) -> None:
    """Echo socket for log streaming."""
    await manager.connect(websocket)
    try:
        while True:
            payload = await websocket.receive_text()
            await manager.broadcast(json.dumps({"echo": payload}))
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)


# ==============================================================================
# Entry Point
# ==============================================================================


def main() -> None:
    """Run the API server."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()


__all__ = ["app", "main"]
