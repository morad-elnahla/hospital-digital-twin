"""FastAPI/uvicorn entry point for the Hospital Digital Twin API and built dashboard.

Runtime configuration is read from environment variables (or a local .env file).
The role comes from the stored account, never from the request. Decisions, sessions,
the sandbox, audit log, and accounts persist under the configured runtime directory.
The synthetic source data remains read-only.
"""
from __future__ import annotations

import json
import hmac
import logging
import os
import socket
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict

from hospital_agents import llm
from hospital_agents.auth import PERMISSIONS, AuthError, Principal
from hospital_agents.twin_data import TwinData

ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"
CONTENT_TYPES = {".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml", ".woff": "font/woff", ".woff2": "font/woff2", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".ico": "image/x-icon"}
CSP = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"


from hospital_agents.service import ApiError, App


# ───────────────────────── FastAPI / ASGI layer ─────────────────────────

class ApiBody(BaseModel):
    model_config = ConfigDict(extra="allow")
    unit: Any = None
    multiplier: Any = None
    demand_multiplier: Any = None
    as_of: Any = None
    horizon: Any = None
    seed: Any = None
    language: Any = None
    interventions: Any = None
    scenario_lab: Any = None
    username: Any = None
    password: Any = None
    note: Any = None
    reason: Any = None
    message: Any = None
    value: Any = None
    approve: Any = None


def _body(payload: ApiBody) -> dict:
    return payload.model_dump(exclude_unset=True)


def _user(principal: Principal) -> dict:
    return {"username": principal.username, "role": principal.role, "role_label": principal.label,
            "permissions": [key for key, roles in PERMISSIONS.items() if principal.role in roles]}


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"time": datetime.now(timezone.utc).isoformat(), "level": record.levelname,
                           "logger": record.name, "event": getattr(record, "event", "log"),
                           "message": record.getMessage(), **getattr(record, "fields", {})}, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(os.environ.get("HDT_LOG_LEVEL", "INFO").upper())


def create_app(service: App | None = None) -> FastAPI:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(web: FastAPI):
        if web.state.service is None:
            runtime = Path(os.environ.get("HDT_RUNTIME_DIR", str(ROOT / "runtime")))
            data_dir = Path(os.environ.get("HDT_DATA_DIR", str(ROOT / "data")))
            if os.environ.get("HDT_RESET_CREDENTIALS", "0") == "1":
                (runtime / "users.json").unlink(missing_ok=True)
                (runtime / "sessions.sqlite").unlink(missing_ok=True)
            if data_dir.resolve() == (ROOT / "data").resolve() and not (runtime / "hdt.sqlite").exists():
                from db.build_db import build
                build(db_path=runtime / "hdt.sqlite")
            web.state.service = App(data_dir, runtime, Path(os.environ.get("HDT_POLICY_DIR", str(ROOT / "policies"))))
            creds = web.state.service.auth.initial_credentials
            if creds:
                logging.getLogger("hdt.auth").warning("first_run_credentials", extra={"event": "auth.bootstrap",
                    "fields": {"accounts": creds}})
        yield

    web = FastAPI(title="Hospital Digital Twin API", version="1.0.0", lifespan=lifespan)
    web.state.service = service

    @web.middleware("http")
    async def security_and_access_log(request: Request, call_next):
        start = time.perf_counter()
        # Older clients omit Content-Type while sending JSON. Normalize that request so
        # FastAPI's Pydantic model and generated OpenAPI schema remain authoritative.
        if request.method in ("POST", "PUT", "PATCH"):
            raw_body = await request.body()
            content_type = request.headers.get("content-type", "")
            if raw_body.lstrip().startswith((b"{", b"[")) and "application/json" not in content_type:
                request.scope["headers"] = [(k, b"application/json" if k.lower() == b"content-type" else v)
                                             for k, v in request.scope["headers"]]
                if not any(k.lower() == b"content-type" for k, _ in request.scope["headers"]):
                    request.scope["headers"].append((b"content-type", b"application/json"))
        try:
            response = await call_next(request)
        except Exception:
            logging.getLogger("hdt.http").exception("request failed", extra={"event": "http.error",
                                         "fields": {"method": request.method, "path": request.url.path}})
            raise
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = CSP
        logging.getLogger("hdt.http").info("request completed", extra={"event": "http.request",
            "fields": {"method": request.method, "path": request.url.path, "status": response.status_code,
                       "duration_ms": round((time.perf_counter() - start) * 1000, 2)}})
        return response

    @web.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError):
        return JSONResponse(status_code=int(exc.status), content={"error": exc.message})

    @web.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, exc: HTTPException):
        message = "not found" if exc.status_code == 404 else str(exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"error": message})

    @web.exception_handler(RequestValidationError)
    async def request_validation_handler(_request: Request, exc: RequestValidationError):
        errors = exc.errors()
        if any(error.get("type") == "json_invalid" for error in errors):
            message = "invalid JSON"
        elif any(error.get("type") == "model_attributes_type" for error in errors):
            message = "JSON object expected"
        else:
            first = errors[0] if errors else {}
            loc = ".".join(str(part) for part in first.get("loc", ())[1:])
            message = "invalid request body" + (f" at {loc}: {first.get('msg', 'invalid value')}" if loc else "")
        return JSONResponse(status_code=400, content={"error": message})

    @web.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception):
        logging.getLogger("hdt.api").exception("unhandled API exception", extra={"event": "api.unhandled"})
        return JSONResponse(status_code=500, content={"error": "internal error"})

    def svc(request: Request) -> App:
        value = request.app.state.service
        if value is None:
            raise ApiError(HTTPStatus.SERVICE_UNAVAILABLE, "application is not ready")
        return value

    def principal(request: Request) -> Principal | None:
        header = request.headers.get("Authorization", "")
        return svc(request).auth.principal(header[7:] if header.startswith("Bearer ") else None)

    def require(request: Request, permission: str) -> Principal:
        return svc(request)._need(principal(request), permission)

    def query_params(request: Request) -> dict[str, list[str]]:
        return {key: request.query_params.getlist(key) for key in request.query_params.keys()}

    @web.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(UI / "dashboard.html", media_type="text/html")

    @web.get("/static/{legacy_path:path}", include_in_schema=False)
    def old_static(legacy_path: str):
        raise ApiError(HTTPStatus.NOT_FOUND, "legacy static assets are not served")

    @web.get("/ui/{asset_path:path}", include_in_schema=False)
    def ui_assets(asset_path: str):
        path = (UI / unquote(asset_path)).resolve()
        if UI.resolve() not in path.parents or path.suffix not in CONTENT_TYPES or not path.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "not found")
        return FileResponse(path, media_type=CONTENT_TYPES[path.suffix])

    @web.post("/api/login", tags=["auth"])
    def login(payload: ApiBody, request: Request):
        a, body = svc(request), _body(payload)
        try:
            token, p = a.auth.login(str(body.get("username", "")), str(body.get("password", "")))
        except AuthError as exc:
            raise ApiError(HTTPStatus(exc.status), exc.message) from None
        a.log(p.username, "auth.login", role=p.role)
        return {"token": token, "user": _user(p)}

    @web.post("/api/logout", tags=["auth"])
    def logout(request: Request):
        p = require(request, "read")
        header = request.headers.get("Authorization", "")
        svc(request).auth.logout(header[7:] if header.startswith("Bearer ") else None)
        return {"ok": True}

    @web.get("/api/me", tags=["auth"])
    def me(request: Request): return _user(require(request, "read"))

    @web.get("/api/meta", tags=["system"])
    def meta(request: Request): require(request, "read"); return svc(request).meta()

    @web.get("/api/overview", tags=["operations"])
    def overview(request: Request): require(request, "read"); return svc(request).overview(query_params(request))

    @web.get("/api/capacity", tags=["operations"])
    def capacity(request: Request): require(request, "read"); return svc(request).capacity(query_params(request))

    @web.get("/api/staff", tags=["operations"])
    def staff(request: Request): require(request, "read"); return svc(request).staff(query_params(request))

    @web.get("/api/or", tags=["operations"])
    def operating_rooms(request: Request): require(request, "read"); return svc(request).operating_rooms(query_params(request))

    @web.get("/api/forecasts", tags=["operations"])
    def forecasts(request: Request): require(request, "read"); return svc(request).forecasts(query_params(request))

    @web.get("/api/alerts", tags=["operations"])
    def alerts(request: Request): require(request, "read"); return svc(request).alerts(query_params(request))

    @web.get("/api/quality", tags=["operations"])
    def quality(request: Request): require(request, "read"); return svc(request).quality()

    @web.get("/api/status", tags=["system"])
    def status(request: Request): require(request, "read"); return svc(request).status()

    @web.get("/api/knowledge", tags=["assistant"])
    def knowledge(request: Request): require(request, "read"); return svc(request).knowledge(query_params(request))

    @web.get("/api/health", tags=["system"])
    def health(request: Request):
        a = svc(request)
        health_token = os.environ.get("HDT_HEALTH_TOKEN", "")
        token = request.headers.get("Authorization", "")
        health_authorized = bool(health_token and hmac.compare_digest(token, f"Bearer {health_token}"))
        if not health_authorized:
            a._need(principal(request), "read")
        return a.health()

    @web.get("/api/twin", tags=["operations"])
    def twin(request: Request): require(request, "read"); return svc(request).twin_map(query_params(request))

    @web.get("/api/assistant", tags=["assistant"])
    def assistant_history(request: Request): return svc(request).assistant_history(require(request, "read"))

    @web.post("/api/assistant", tags=["assistant"])
    def assistant_ask(payload: ApiBody, request: Request): return svc(request).assistant_ask(_body(payload), require(request, "read"))

    @web.post("/api/assistant/reset", tags=["assistant"])
    def assistant_reset(request: Request): return svc(request).assistant_reset(require(request, "read"))

    @web.post("/api/llm-test", tags=["assistant"])
    def llm_test(request: Request): return svc(request).llm_test(require(request, "run"))

    @web.get("/api/decisions", tags=["decisions"])
    def decisions(request: Request): require(request, "read"); return svc(request).decisions(request.query_params.get("lang"))

    @web.get("/api/decisions/{decision_id}", tags=["decisions"])
    def decision_detail(decision_id: str, request: Request):
        require(request, "read")
        return svc(request).view(decision_id, request.query_params.get("lang"))

    @web.post("/api/decisions/{decision_id}/{action}", tags=["decisions"])
    def decision_action(decision_id: str, action: str, payload: ApiBody, request: Request):
        if action not in ("approve", "reject", "acknowledge-escalation"):
            raise ApiError(HTTPStatus.NOT_FOUND, "not found")
        a = svc(request)
        method = "acknowledge_escalation" if action == "acknowledge-escalation" else action
        return getattr(a, method)(decision_id, _body(payload), principal(request))

    @web.get("/api/sandbox", tags=["decisions"])
    def sandbox(request: Request): require(request, "read"); return svc(request).sandbox()

    @web.get("/api/audit", tags=["decisions"])
    def audit(request: Request): require(request, "read"); return svc(request).audit_tail()

    @web.get("/api/policies", tags=["policies"])
    def policies(request: Request): require(request, "read"); return svc(request).policies()

    @web.post("/api/policies", tags=["policies"])
    def set_policy(payload: ApiBody, request: Request): return svc(request).set_policy(_body(payload), principal(request))

    @web.get("/api/scenario-drafts", tags=["scenarios"])
    def scenario_drafts(request: Request): return svc(request).list_scenario_drafts(require(request, "run"))

    @web.post("/api/scenario-drafts", tags=["scenarios"])
    def save_scenario_draft(payload: ApiBody, request: Request): return svc(request).save_scenario_draft(_body(payload), require(request, "run"))

    @web.post("/api/simulate", tags=["scenarios"])
    def simulate(payload: ApiBody, request: Request): return svc(request).simulate(_body(payload), require(request, "run"))

    @web.post("/api/run", tags=["agents"])
    def run_agents(payload: ApiBody, request: Request): return svc(request).run(_body(payload), require(request, "run"))

    @web.post("/api/rollback", tags=["decisions"])
    def rollback(payload: ApiBody, request: Request): return svc(request).rollback(_body(payload), principal(request))

    @web.post("/api/simulations/{simulation_id}/replay", tags=["scenarios"])
    def replay(simulation_id: str, request: Request):
        require(request, "run")
        return svc(request).replay_simulation(simulation_id)

    @web.get("/{spa_path:path}", include_in_schema=False)
    def spa_fallback(spa_path: str):
        if spa_path == "api" or spa_path.startswith("api/") or "." in spa_path.rsplit("/", 1)[-1]:
            raise ApiError(HTTPStatus.NOT_FOUND, "not found")
        return FileResponse(UI / "dashboard.html", media_type="text/html")

    return web


app = create_app()


class Handler:
    """Compatibility holder used by legacy integration tests; HTTP is served by FastAPI."""
    app: App


class UvicornTestServer:
    """Thread-compatible ephemeral Uvicorn server for the existing HTTP integration suite."""
    def __init__(self, service: App, host: str, port: int):
        self.service = service
        self._thread: threading.Thread | None = None
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((host, port))
        self.socket.listen(128)
        self.server_address = self.socket.getsockname()
        self.server = uvicorn.Server(uvicorn.Config(create_app(service), host=host, port=self.server_address[1],
                                                     log_config=None, access_log=False, lifespan="on"))
        self.RequestHandlerClass = type("RequestHandlerClass", (), {"app": service})

    def serve_forever(self, poll_interval: float = 0.1) -> None:
        del poll_interval
        self._thread = threading.current_thread()
        self.server.run(sockets=[self.socket])

    def shutdown(self) -> None:
        self.server.should_exit = True
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)

    def server_close(self) -> None:
        try:
            self.socket.close()
        except OSError:
            pass


def make_server(data_dir: Path, port: int = 8000, host: str = "127.0.0.1", *,
                runtime: Path = ROOT / "runtime", policy_dir: Path = ROOT / "policies") -> UvicornTestServer:
    # Preserve the test seam used by the previous app.py facade.
    import hospital_agents.service as service_module
    service_module.TwinData = TwinData
    Handler.app = App(Path(data_dir), runtime, policy_dir)
    return UvicornTestServer(Handler.app, host, port)


def main() -> None:
    llm.load_env(ROOT / ".env")
    configure_logging()
    host = os.environ.get("HDT_HOST", "127.0.0.1")
    port = int(os.environ.get("HDT_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
