"""FastAPI app: runs the sim loop and streams state to the big screen and phones.

Run:  uvicorn deadzone.app:app --host 0.0.0.0 --port 8000
"""
import asyncio
import base64
import ipaddress
import json
import math
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
from .command.controls import FaultRequest, RelayPlace, RelayPower, director_adapter
from .command.reports import local_report
from .command.safety import SafetyChecker
from .robot.robot import resume_command
from .robot.perception import CROP_DIR, get_detector
from .sim import DT, ROBOT_DEFS, Sim

MAPS_EVERY = 5
MAX_PHONE_RELAYS = 32
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def detector_status():
    detector = get_detector()
    status = {"detector": detector.mode}
    if detector.mode == "sim":
        status["detector_reason"] = detector.reason
    return status


class Hub:
    def __init__(self):
        self.sim = Sim(n_robots=int(os.environ.get("DZ_ROBOTS", "1")), seed=int(os.environ.get("DZ_SEED", "7")))
        self.sim.tick()  # real sensor/bundle delivery before the paused QR/plan demo beat
        self.running = False
        self.speed = float(os.environ.get("DZ_SPEED", "2"))
        self.screens: set[WebSocket] = set()
        self.phones: set[WebSocket] = set()
        self.phone_sessions = {}
        self.relay_clients = {}
        self.relay_power_requests = {}
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
        return self.envelope("hello", self.sim.hello() | {"speed": self.speed, "running": self.running}
                             | detector_status())

    def phone_hello(self, client, role):
        robots = [{"id": rid, "name": name, "color": color,
                   "capabilities": {"stairs": self.sim.robot_specs[rid].stairs,
                                    "max_rubble_height": self.sim.robot_specs[rid].max_rubble_height}}
                  for rid, name, color in ROBOT_DEFS if rid in self.sim.robot_specs]
        return {"floorplan": self.sim.prior.planning_data(),
                "grid": {"w": self.sim.prior.w, "h": self.sim.prior.h, "cell": self.sim.prior.cell},
                "robots": robots, "plan": self.plans.current(), "client": client, "role": role,
                "relay_id": self.relay_clients.get(client) if role == "relay" else None,
                **detector_status()}

    def attach_relay(self, client):
        if client not in self.relay_clients:
            if sum(bool(r["phone"]) for r in self.sim.relays.values()) >= MAX_PHONE_RELAYS:
                raise PlanError("relay_limit", "Reset the simulation before adding more phone relays", 409)
            self.relay_clients[client] = self.sim.add_relay(self.sim.prior.entry, owner=client, phone=True)
        rid = self.relay_clients[client]
        self.sim.set_relay_power(rid, self.relay_power_requests.setdefault(client, True))
        return rid

    def relay_state(self, client):
        rid = self.relay_clients[client]
        relay = self.sim.relays[rid]
        return {"id": rid, "on": relay["on"], "pos": list(relay["pos"]),
                "queue": len(self.sim.network.queues[rid]),
                "neighbors": [{"id": node, "rssi": round(rssi, 1)}
                              for node, rssi in sorted(self.sim.links.neighbors(rid))]}

    async def relay_states(self):
        for ws, (client, role) in list(self.phone_sessions.items()):
            if role == "relay":
                try:
                    await ws.send_text(self.envelope("relay_state", self.relay_state(client)))
                except (RuntimeError, WebSocketDisconnect):
                    await self.disconnect_phone(ws, notify=False)

    async def disconnect_phone(self, ws, notify=True):
        session = self.phone_sessions.pop(ws, None)
        self.phones.discard(ws)
        if session is not None:
            client, role = session
            if role == "relay" and client in self.relay_clients and (client, role) not in self.phone_sessions.values():
                self.sim.set_relay_power(self.relay_clients[client], False)
                if notify:
                    await self.relay_states()

    async def plan_state(self, state):
        message = self.envelope("plan_state", state)
        await self.send_all(self.phones, message)
        await self.send_all(self.screens, message)

    async def dispatch(self, plan_id):
        was_dispatched = plan_id in self.plans.dispatched
        result = self.plans.dispatch(plan_id)
        if result["ok"]:
            await self.plan_state(self.plans.get(plan_id).model_dump(mode="json"))
            if not was_dispatched:
                await self.send_all(self.screens, self.envelope("event", {
                    "kind": "plan_dispatched", "plan_id": plan_id}))
        else:
            await self.send_all(self.phones, self.envelope("safety", result))
            await self.send_all(self.screens, self.envelope("event", {"kind": "safety_reject", **result}))
        return result

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
        if role == "relay" and kind in ("relay_place", "relay_power"):
            rid = self.relay_clients[client]
            if kind == "relay_power":
                power = RelayPower.model_validate(data)
                self.relay_power_requests[client] = power.on
                self.sim.set_relay_power(rid, power.on)
            else:
                placement = RelayPlace.model_validate(data)
                try:
                    self.sim.move_relay(rid, placement.pos)
                except ValueError as error:
                    raise PlanError("invalid_relay_position", str(error), 422) from None
            await self.relay_states()
            return
        if role != "planner":
            raise PlanError("read_only_role", "Relay sessions cannot edit or submit search plans", 403)
        if kind == "plan_edit":
            plan = SearchPlan.model_validate({**data, "author": client})
            state = self.plans.save(plan)
            await self.plan_state(state)
        elif kind == "plan_submit":
            ref = PlanRef.model_validate(data)
            await self.check_plan(ref.plan_id)
        else:
            raise PlanError("unsupported_message", f"Unsupported phone message: {kind}", 422)

    async def broadcast_tick(self, force_maps=False):
        snap = self.sim.snapshot()
        await self.send_all(self.screens, self.envelope("tick", snap))
        if force_maps or self.sim.tick_n % MAPS_EVERY == 0:
            await self.send_all(self.screens, self.envelope("maps", self.sim.maps()))
            await self.send_all(self.phones, self.envelope("cmd_view", self.phone_view()))
            await self.relay_states()
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
            self.sim.tick()
            self._init_plans()
            self.relay_clients.clear()
            self.relay_power_requests.clear()
            for client, role in sorted(set(self.phone_sessions.values())):
                if role == "relay":
                    self.attach_relay(client)
            await self.send_all(self.screens, self.hello())
            await self.send_all(self.screens, self.envelope("maps", self.sim.maps()))
            await self.send_all(self.screens, self.envelope("plan_state", None))
            for ws, (client, role) in list(self.phone_sessions.items()):
                try:
                    await ws.send_text(self.envelope("hello", self.phone_hello(client, role)))
                except (RuntimeError, WebSocketDisconnect):
                    await self.disconnect_phone(ws, notify=False)
            await self.broadcast_tick(force_maps=True)
            return
        elif action == "speed":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise PlanError("invalid_speed", "Speed must be a finite positive number", 422)
            self.speed = max(0.25, min(10.0, float(value)))
        elif action == "director":
            if not isinstance(value, dict) or "type" in value:
                raise PlanError("invalid_director", "Director value must use do, not type", 422)
            request = director_adapter.validate_python({
                "type": value.get("do"), **{k: v for k, v in value.items() if k != "do"}})
            if request.type in ("overload", "resume"):
                if request.robot not in self.sim.robots:
                    raise PlanError("robot_not_found", f"Unknown robot: {request.robot}", 404)
                if request.type == "overload":
                    self.sim.robots[request.robot].inject_perception_overload()
                else:
                    self.sim.network.queues["CMD"].append(resume_command(request.robot, self.sim.time))
            else:
                await self.inject_fault(request)
        else:
            raise PlanError("unknown_control", "Unknown control action", 422)
        await self.send_all(self.screens, self.envelope("control", {"running": self.running, "speed": self.speed}))

    async def inject_fault(self, fault):
        if fault.type == "overcurrent":
            if fault.robot not in self.sim.robots:
                raise PlanError("robot_not_found", f"Unknown robot: {fault.robot}", 404)
            until = self.sim.inject_overcurrent(fault.robot, fault.duration_s)
            result = {"ok": True, "type": "overcurrent", "robot": fault.robot, "until": until}
        else:
            x, y = fault.at
            if not (0 <= x < self.sim.fp.W and 0 <= y < self.sim.fp.H):
                raise PlanError("invalid_fault_position", "Rubble position must be inside the floor plan", 422)
            self.sim.drop_rubble(fault.at, fault.size)
            await self.send_all(self.screens, self.hello())
            result = {"ok": True, "type": "rubble", "at": list(fault.at)}
        await self.broadcast_tick()
        return result

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


@app.exception_handler(ValidationError)
async def control_validation_error(request, error):
    return await request_error(request, error)


@app.get("/api/health")
def health():
    return {"ok": True, "tick": hub.sim.tick_n, "time": hub.sim.time, "running": hub.running}


@app.get("/api/floorplan")
def floorplan():
    return JSONResponse(hub.sim.prior.planning_data())


@app.post("/api/plan")
async def save_plan(plan: SearchPlan):
    state = hub.plans.save(plan)
    await hub.plan_state(state)
    return await hub.check_plan(plan.plan_id)


@app.post("/api/dispatch")
async def dispatch_plan(ref: PlanRef):
    return await hub.dispatch(ref.plan_id)


@app.post("/api/fault")
async def inject_fault(fault: FaultRequest):
    return await hub.inject_fault(fault)


@app.get("/api/report")
async def report():
    result = local_report(hub.sim.post, hub.sim.time)
    await hub.send_all(hub.screens, hub.envelope("report", result))
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
    await ws.send_text(hub.envelope("plan_state", hub.plans.current()))
    try:
        while True:
            try:
                msg = json.loads(await ws.receive_text())
                if not isinstance(msg, dict) or not isinstance(msg.get("data"), dict):
                    raise PlanError("invalid_message", "Expected an envelope with object data", 422)
                if msg.get("t") == "control":
                    d = msg["data"]
                    await hub.control(d.get("action"), d.get("value"))
            except (PlanError, ValidationError, json.JSONDecodeError) as error:
                data = {"code": "invalid_message", "msg": "Invalid screen control"}
                if isinstance(error, PlanError):
                    data = {"code": error.code, "msg": str(error)}
                elif isinstance(error, ValidationError):
                    data["issues"] = validation_issues(error)
                await ws.send_text(hub.envelope("error", data))
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
        if role == "relay":
            hub.attach_relay(client)
        await ws.send_text(hub.envelope("hello", hub.phone_hello(client, role)))
        await ws.send_text(hub.envelope("cmd_view", hub.phone_view()))
        if role == "relay":
            await ws.send_text(hub.envelope("relay_state", hub.relay_state(client)))
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
    except PlanError as error:
        await ws.send_text(hub.envelope("error", {"code": error.code, "msg": str(error)}))
        await ws.close(code=1008)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect_phone(ws)


@app.get("/phone", include_in_schema=False)
@app.get("/phone/", include_in_schema=False)
def phone_page():
    index = WEB_DIST / "index.html"
    if not index.exists():
        raise HTTPException(503, "Build the frontend or use the Vite frontend address")
    return FileResponse(index)


app.mount("/crops", StaticFiles(directory=CROP_DIR), name="crops")


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
