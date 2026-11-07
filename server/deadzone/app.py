"""FastAPI app: runs the sim loop and streams state to the big screen and phones.

Run:  uvicorn deadzone.app:app --host 0.0.0.0 --port 8000
"""
import asyncio
import base64
import ipaddress
import json
import os
import socket
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .command.plan import PlanError, PlanManager, PlanRef, SearchPlan
from .command.safety import SafetyChecker
from .sim import DT, ROBOT_DEFS, Sim

MAPS_EVERY = 5
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


class Hub:
    def __init__(self):
        self.sim = Sim(n_robots=int(os.environ.get("DZ_ROBOTS", "1")), seed=int(os.environ.get("DZ_SEED", "7")))
        self.running = False
        self.speed = float(os.environ.get("DZ_SPEED", "2"))
        self.screens: set[WebSocket] = set()
        self.phones: set[WebSocket] = set()
        self.phone_sessions = {}
        self.next_phone_id = 1
        self.seq = 0
        self._init_plans()

    def _init_plans(self):
        checker = SafetyChecker(self.sim.prior, self.sim.robot_specs, self.sim.energy_time_scale)
        self.plans = PlanManager(self.sim, checker)

    def envelope(self, t, data):
        self.seq += 1
        return json.dumps({"t": t, "seq": self.seq, "time": self.sim.time, "data": data},
                          separators=(",", ":"))

    async def send_all(self, clients, msg):
        dead = []
        for ws in list(clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            clients.discard(ws)

    def hello(self):
        return self.envelope("hello", self.sim.hello() | {"speed": self.speed, "running": self.running})

    def phone_hello(self, client, role):
        robots = [{"id": rid, "name": name, "color": color,
                   "capabilities": {"stairs": self.sim.robot_specs[rid].stairs,
                                    "max_rubble_height": self.sim.robot_specs[rid].max_rubble_height}}
                  for rid, name, color in ROBOT_DEFS if rid in self.sim.robot_specs]
        return {"floorplan": self.sim.prior.planning_data(),
                "grid": {"w": self.sim.prior.w, "h": self.sim.prior.h, "cell": self.sim.prior.cell},
                "robots": robots, "plan": self.plans.current(), "client": client, "role": role,
                "relay_id": None}

    def phone_view(self):
        # Do not call snapshot() here: phones need no Reality objects at all.
        return self.sim.post.view(self.sim.time) | {
            "map": base64.b64encode(self.sim.post.map.tobytes()).decode()}

    async def check_plan(self, plan_id):
        result = self.plans.check(plan_id)
        await self.send_all(self.phones, self.envelope("safety", result))
        if not result["ok"]:
            await self.send_all(self.screens, self.envelope("event", {"kind": "safety_reject", **result}))
        return result

    async def phone_message(self, message, client, role):
        if not isinstance(message, dict) or not isinstance(message.get("data"), dict):
            raise PlanError("invalid_message", "Expected an envelope with object data", 422)
        kind, data = message.get("t"), message["data"]
        if role != "planner":
            raise PlanError("read_only_role", "Relay sessions are read-only in this milestone", 403)
        if kind == "plan_edit":
            plan = SearchPlan.model_validate({**data, "author": client})
            state = self.plans.save(plan)
            await self.send_all(self.phones, self.envelope("plan_state", state))
        elif kind == "plan_submit":
            ref = PlanRef.model_validate(data)
            await self.check_plan(ref.plan_id)
        else:
            raise PlanError("unsupported_message", f"Unsupported phone message: {kind}", 422)

    async def broadcast_tick(self):
        snap = self.sim.snapshot()
        await self.send_all(self.screens, self.envelope("tick", snap))
        if self.sim.tick_n % MAPS_EVERY == 0:
            await self.send_all(self.screens, self.envelope("maps", self.sim.maps()))
            await self.send_all(self.phones, self.envelope("cmd_view", self.phone_view()))
        for ev in self.sim.drain_events():
            await self.send_all(self.screens, self.envelope("event", ev))

    async def control(self, action, value=None):
        if action == "start":
            self.running = True
        elif action == "pause":
            self.running = False
        elif action == "toggle":
            self.running = not self.running
        elif action == "reset":
            self.running = False
            self.sim.reset()
            self._init_plans()
            await self.send_all(self.screens, self.hello())
            await self.send_all(self.screens, self.envelope("maps", self.sim.maps()))
            for ws, (client, role) in list(self.phone_sessions.items()):
                try:
                    await ws.send_text(self.envelope("hello", self.phone_hello(client, role)))
                except (RuntimeError, WebSocketDisconnect):
                    self.phones.discard(ws)
                    self.phone_sessions.pop(ws, None)
            await self.broadcast_tick()
            return
        elif action == "speed":
            self.speed = max(0.25, min(10.0, float(value)))
        elif action == "director" and isinstance(value, dict) and value.get("do") == "rubble":
            self.sim.drop_rubble(value["at"])
            await self.send_all(self.screens, self.hello())
        await self.send_all(self.screens, self.envelope("control", {"running": self.running, "speed": self.speed}))

    async def loop(self):
        next_t = time.perf_counter()
        while True:
            if self.running:
                self.sim.tick()
                await self.broadcast_tick()
            next_t += DT / self.speed
            delay = next_t - time.perf_counter()
            if delay < -0.5:          # fell behind (laptop busy), don't spiral
                next_t = time.perf_counter()
            await asyncio.sleep(max(0.0, delay))


hub = Hub()


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(hub.loop())
    if os.environ.get("DZ_AUTOSTART") == "1":
        hub.running = True
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Deadzone sim", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def validation_issues(error):
    # Do not echo arbitrary input, NaN or non-serializable validator contexts.
    return [{"loc": list(issue["loc"]), "msg": issue["msg"]} for issue in error.errors()]


@app.exception_handler(PlanError)
async def plan_error(request, error):
    return JSONResponse(status_code=error.status, content={"detail": {"code": error.code, "msg": str(error)}})


@app.exception_handler(RequestValidationError)
async def request_error(request, error):
    return JSONResponse(status_code=422, content={"detail": {"code": "invalid_request",
                        "msg": "Request validation failed", "issues": validation_issues(error)}})


@app.get("/api/health")
def health():
    return {"ok": True, "tick": hub.sim.tick_n, "time": hub.sim.time, "running": hub.running}


@app.get("/api/floorplan")
def floorplan():
    return JSONResponse(hub.sim.prior.planning_data())


@app.post("/api/plan")
async def save_plan(plan: SearchPlan):
    state = hub.plans.save(plan)
    await hub.send_all(hub.phones, hub.envelope("plan_state", state))
    return await hub.check_plan(plan.plan_id)


@app.post("/api/dispatch")
async def dispatch_plan(ref: PlanRef):
    result = hub.plans.dispatch(ref.plan_id)
    if not result["ok"]:
        await hub.send_all(hub.phones, hub.envelope("safety", result))
        await hub.send_all(hub.screens, hub.envelope("event", {"kind": "safety_reject", **result}))
    return result


@app.get("/api/join")
def join(request: Request):
    configured = os.environ.get("DZ_PUBLIC_URL")
    try:
        parts = urlsplit(configured or str(request.base_url))
        port = parts.port
    except ValueError:
        raise HTTPException(503, "Set DZ_PUBLIC_URL to a valid HTTP(S) frontend origin") from None
    if (parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password
            or (configured and (parts.path not in ("", "/") or parts.query or parts.fragment))):
        raise HTTPException(503, "Set DZ_PUBLIC_URL to the public HTTP(S) frontend address")
    if not configured and parts.hostname in ("localhost", "127.0.0.1", "::1"):
        try:
            addresses = socket.gethostbyname_ex(socket.gethostname())[2]
            address = next(a for a in sorted(addresses)
                           if ipaddress.ip_address(a).is_private and not ipaddress.ip_address(a).is_loopback
                           and not ipaddress.ip_address(a).is_link_local)
        except (OSError, StopIteration):
            raise HTTPException(503, "Set DZ_PUBLIC_URL to the laptop's LAN frontend address") from None
        parts = parts._replace(netloc=f"{address}:{port or (443 if parts.scheme == 'https' else 80)}")
    url = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") + "/phone", "", ""))
    return {"url": url}


@app.post("/api/control")
async def control(body: dict):
    await hub.control(body.get("action"), body.get("value"))
    return {"ok": True, "running": hub.running, "speed": hub.speed}


@app.websocket("/ws/screen")
async def ws_screen(ws: WebSocket):
    await ws.accept()
    hub.screens.add(ws)
    await ws.send_text(hub.hello())
    await ws.send_text(hub.envelope("maps", hub.sim.maps()))
    await ws.send_text(hub.envelope("tick", hub.sim.snapshot()))
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("t") == "control":
                d = msg.get("data", {})
                await hub.control(d.get("action"), d.get("value"))
    except (WebSocketDisconnect, RuntimeError, json.JSONDecodeError):
        pass
    finally:
        hub.screens.discard(ws)


@app.websocket("/ws/phone")
async def ws_phone(ws: WebSocket,
                   client: str | None = Query(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$"),
                   role: Literal["planner", "relay"] = "planner"):
    """Phone planning session; only prior geometry and delivered Command data."""
    await ws.accept()
    if client is None:
        client = f"phone-{hub.next_phone_id}"
        hub.next_phone_id += 1
    hub.phones.add(ws)
    hub.phone_sessions[ws] = client, role
    try:
        await ws.send_text(hub.envelope("hello", hub.phone_hello(client, role)))
        await ws.send_text(hub.envelope("cmd_view", hub.phone_view()))
        while True:
            try:
                message = json.loads(await ws.receive_text())
                await hub.phone_message(message, client, role)
            except (ValidationError, PlanError, json.JSONDecodeError) as error:
                data = {"code": "invalid_plan", "msg": "Plan validation failed"}
                if isinstance(error, ValidationError):
                    data["issues"] = validation_issues(error)
                elif isinstance(error, PlanError):
                    data = {"code": error.code, "msg": str(error)}
                else:
                    data = {"code": "invalid_json", "msg": "Message must be valid JSON"}
                await ws.send_text(hub.envelope("error", data))
    except WebSocketDisconnect:
        pass
    finally:
        hub.phones.discard(ws)
        hub.phone_sessions.pop(ws, None)


@app.get("/phone", include_in_schema=False)
@app.get("/phone/", include_in_schema=False)
def phone_page():
    index = WEB_DIST / "index.html"
    if not index.exists():
        raise HTTPException(503, "Build the frontend or use the Vite frontend address")
    return FileResponse(index)


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
