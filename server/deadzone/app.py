"""FastAPI app: runs the sim loop and streams state to the big screen and phones.

Run:  uvicorn deadzone.app:app --host 0.0.0.0 --port 8000
"""
import asyncio
import base64
import ipaddress
import json
import math
import os
import secrets
import socket
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .ai_lab import AILabAssets
from .command.plan import PlanError, PlanManager, PlanRef, SearchPlan
from .command.crdt import MergeBatch, PlanSync
from .command.leases import LeaseClaim, LeaseTable, PresenterRelease, RobotRef, VoiceRequest
from .command.controls import AskQuestion, FaultRequest, RelayPlace, RelayPower, director_adapter
from .command.reports import command_report
from .command.rescue_order import rescue_order
from .command.safety import SafetyChecker
from .robot.robot import resume_command
from .robot.perception import CROP_DIR, get_detector
from .sim import DT, ROBOT_DEFS, Sim

MAPS_EVERY = 5
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
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
        self.plan_lock = asyncio.Lock()  # survives reset: old publications finish first
        self.lease_lock = asyncio.Lock()
        self.leases = LeaseTable(self.sim.robots)
        self.controller_sockets = {}
        self._init_plans()

    def _init_plans(self):
        checker = SafetyChecker(self.sim.prior, self.sim.robot_specs, self.sim.energy_time_scale)
        self.plans = PlanManager(self.sim, checker)
        self.plan_sync = PlanSync(self.plans)

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

    def leases_enabled(self):
        return os.environ.get("DZ_CONTROL_LEASES") == "1" or os.environ.get("DZ_VOICE") == "1"

    def require_leases(self):
        if not self.leases_enabled():
            raise PlanError("feature_disabled", "Enable DZ_CONTROL_LEASES=1 for control leases", 409)

    def register_controller(self, ws, client):
        if self.leases_enabled():
            self.controller_sockets[ws] = self.leases.register(client)

    def controller_hello(self, ws):
        token = self.controller_sockets.get(ws)
        return {"controller_token": token} if token else {}

    def lease_state(self):
        return self.leases.snapshot(self.leases_enabled())

    async def broadcast_leases(self):
        if not self.leases_enabled():
            return
        message = self.envelope("leases", self.lease_state())
        await self.send_all(self.phones, message)
        await self.send_all(self.screens, message)

    async def sweep_leases(self):
        async with self.lease_lock:
            if self.leases.expire():
                await self.broadcast_leases()

    async def disconnect_controller(self, ws):
        async with self.lease_lock:
            token = self.controller_sockets.pop(ws, None)
            if token and self.leases.disconnect(token):
                await self.broadcast_leases()

    async def change_lease(self, action, body, token=None):
        self.require_leases()
        async with self.lease_lock:
            if self.leases.expire():
                await self.broadcast_leases()
            if action == "override":
                expected = os.environ.get("DZ_PRESENTER_TOKEN", "")
                if not expected or not secrets.compare_digest(expected.encode(), body.presenter_token.encode()):
                    raise PlanError("presenter_required", "Presenter credential required", 403)
                self.leases.override(body.robot)
            elif action == "claim":
                self.leases.claim(body.robot, token, body.name)
            else:
                getattr(self.leases, action)(body.robot, token)
            await self.broadcast_leases()
            return self.lease_state()

    def authorize_robot(self, robot, token):
        if self.leases_enabled():
            self.leases.require(robot, token)

    def hello(self, ws=None):
        return self.envelope("hello", self.sim.hello() | self.control_state()
                             | detector_status() | {"leases": self.lease_state()}
                             | self.controller_hello(ws))

    def control_state(self):
        modes = {r.mode for r in self.sim.robots.values()}
        return {"running": self.running, "speed": self.speed,
                "mode": next(iter(modes)) if len(modes) == 1 else "mixed"}

    def phone_hello(self, client, role):
        robots = [{"id": rid, "name": name, "color": color,
                   "capabilities": {"stairs": self.sim.robot_specs[rid].stairs,
                                    "max_rubble_height": self.sim.robot_specs[rid].max_rubble_height}}
                  for rid, name, color in ROBOT_DEFS if rid in self.sim.robot_specs]
        return {"floorplan": self.sim.prior.planning_data(),
                "grid": {"w": self.sim.prior.w, "h": self.sim.prior.h, "cell": self.sim.prior.cell},
                "robots": robots, "plan": self.plans.current(), "client": client, "role": role,
                "relay_id": self.relay_clients.get(client) if role == "relay" else None,
                "leases": self.lease_state(),
                **detector_status()}

    def attach_relay(self, client):
        if client not in self.relay_clients:
            if sum(bool(r["phone"]) for r in self.sim.relays.values()) >= MAX_PHONE_RELAYS:
                raise PlanError("relay_limit", "Reset the simulation before adding more phone relays", 409)
            self.relay_clients[client] = self.sim.add_relay(self.sim.prior.entry, owner=client, phone=True)
        rid = self.relay_clients[client]
        if self.sim.relays[rid].get("destroyed"):
            raise PlanError("relay_destroyed", "This relay was destroyed; reset to restore it", 409)
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
        await self.disconnect_controller(ws)
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

    async def save_plan(self, plan, check=True):
        async with self.plan_lock:
            state = self.plans.save(plan)
            self.plan_sync.invalidate(plan.plan_id)
            await self.plan_state(state)
            if check:
                return await self._check_plan(plan.plan_id)
            return {"saved": True, "plan_id": plan.plan_id, "checked": False}

    async def dispatch(self, plan_id):
        async with self.plan_lock:
            return await self._dispatch(plan_id)

    async def _dispatch(self, plan_id):
        self.plan_sync.assert_valid(plan_id)
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
        async with self.plan_lock:
            return await self._check_plan(plan_id)

    async def _check_plan(self, plan_id):
        self.plan_sync.assert_valid(plan_id)
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
                if power.on and self.sim.relays[rid].get("destroyed"):
                    raise PlanError("relay_destroyed", "Destroyed relay cannot be powered on", 409)
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
            await self.save_plan(plan, check=False)
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

    async def reset(self):
        async with self.plan_lock:
            async with self.lease_lock:
                self.running = False
                self.sim.reset()
                self.sim.tick()
                self._init_plans()
                self.leases.reset()
                await self.broadcast_leases()
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
                    await ws.send_text(self.envelope("hello", self.phone_hello(client, role) | self.controller_hello(ws)))
                except (RuntimeError, WebSocketDisconnect):
                    await self.disconnect_phone(ws, notify=False)
            await self.broadcast_tick(force_maps=True)
            return

    async def control_message(self, data):
        """Normalize the board's mode alias identically on REST and WebSocket."""
        value = data.get("value")
        if data.get("action") == "mode" and "mode" in data:
            if "value" in data and value != data["mode"]:
                raise PlanError("invalid_mode", "mode and value must agree", 422)
            value = data["mode"]
        await self.control(data.get("action"), value, controller_token=data.get("controller_token"))

    async def control(self, action, value=None, *, controller_token=None):
        if action == "start":
            self.running = True
        elif action == "pause":
            self.running = False
        elif action == "toggle":
            self.running = not self.running
        elif action == "reset":
            await self.reset()
            return
        elif action == "speed":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise PlanError("invalid_speed", "Speed must be a finite positive number", 422)
            self.speed = max(0.25, min(10.0, float(value)))
        elif action == "mode":
            if value not in ("baseline", "deadzone"):
                raise PlanError("invalid_mode", "Mode must be baseline or deadzone", 422)
            for rid in self.sim.robots:
                self.authorize_robot(rid, controller_token)
            for robot in self.sim.robots.values():
                robot.set_mode(value)
        elif action == "director":
            if not isinstance(value, dict) or "type" in value:
                raise PlanError("invalid_director", "Director value must use do, not type", 422)
            request = director_adapter.validate_python({
                "type": value.get("do"), **{k: v for k, v in value.items() if k != "do"}})
            if request.type == "aftershock":
                if os.environ.get("DZ_AFTERSHOCK") != "1":
                    raise PlanError("feature_disabled", "Enable DZ_AFTERSHOCK=1 for an aftershock dry run", 409)
                try:
                    self.sim.aftershock(request.at, request.relay)
                except ValueError as error:
                    raise PlanError("invalid_aftershock", str(error), 422) from None
                await self.send_all(self.screens, self.hello())
                await self.broadcast_tick(force_maps=True)
            elif request.type in ("overload", "resume"):
                if request.robot not in self.sim.robots:
                    raise PlanError("robot_not_found", f"Unknown robot: {request.robot}", 404)
                if request.type == "overload":
                    self.sim.robots[request.robot].inject_perception_overload()
                else:
                    self.authorize_robot(request.robot, controller_token)
                    self.sim.network.queues["CMD"].append(resume_command(request.robot, self.sim.time))
            else:
                await self.inject_fault(request)
        else:
            raise PlanError("unknown_control", "Unknown control action", 422)
        await self.send_all(self.screens, self.envelope("control", self.control_state()))

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
            await self.sweep_leases()
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


@app.get("/api/leases")
async def lease_state():
    await hub.sweep_leases()
    return hub.lease_state()


@app.post("/api/leases/claim")
async def claim_lease(body: LeaseClaim, request: Request):
    return await hub.change_lease("claim", body, request.headers.get("x-controller-token"))


@app.post("/api/leases/heartbeat")
async def heartbeat_lease(body: RobotRef, request: Request):
    return await hub.change_lease("heartbeat", body, request.headers.get("x-controller-token"))


@app.post("/api/leases/release")
async def release_lease(body: RobotRef, request: Request):
    return await hub.change_lease("release", body, request.headers.get("x-controller-token"))


@app.post("/api/leases/override")
async def override_lease(body: PresenterRelease):
    return await hub.change_lease("override", body)


@app.post("/api/robot-command")
async def robot_command(body: dict, request: Request):
    hub.require_leases()
    # Only the existing radio-delivered resume action is implemented here.
    ref = RobotRef.model_validate({"robot": body.get("robot")})
    if body.get("action") != "resume" or set(body) != {"robot", "action"}:
        raise PlanError("unsupported_command", "Only resume is available until the robot command contract lands", 422)
    await hub.control("director", {"do": "resume", "robot": ref.robot},
                      controller_token=request.headers.get("x-controller-token"))
    return {"queued": True, "robot": ref.robot, "action": "resume"}


@app.post("/api/voice")
async def voice(body: VoiceRequest, request: Request):
    # Fail closed until speech/intent and Rayan's action/ack contract are wired.
    hub.require_leases()
    hub.leases.require(body.robot, request.headers.get("x-controller-token"))
    if os.environ.get("DZ_VOICE") != "1":
        raise PlanError("feature_disabled", "Enable DZ_VOICE=1 for voice control", 409)
    raise PlanError("voice_not_ready", "Speech/intent and robot action acknowledgements are not wired yet", 501)


@app.get("/api/floorplan")
def floorplan():
    return JSONResponse(hub.sim.prior.planning_data())


@app.post("/api/plan")
async def save_plan(plan: SearchPlan, check: bool = True):
    return await hub.save_plan(plan, check=check)


def require_plan_sync():
    if os.environ.get("DZ_CRDT") != "1":
        raise PlanError("feature_disabled", "Enable DZ_CRDT=1 for an offline planning dry run", 409)


async def publish_sync(state):
    # Callers hold hub.plan_lock across mutation and the complete publication.
    planners = {ws for ws, (_, role) in hub.phone_sessions.items() if role == "planner"}
    await hub.send_all(planners, hub.envelope("plan_sync", state))
    if state["valid"]:
        await hub.plan_state(state["plan"])
    return state


@app.put("/api/plan-sync")
async def seed_sync(plan: SearchPlan):
    require_plan_sync()
    async with hub.plan_lock:
        return await publish_sync(hub.plan_sync.seed(plan))


@app.get("/api/plan-sync")
async def read_sync(plan_id: str):
    require_plan_sync()
    return hub.plan_sync.state(PlanRef(plan_id=plan_id).plan_id)


@app.post("/api/plan-sync")
async def merge_sync(batch: MergeBatch):
    require_plan_sync()
    async with hub.plan_lock:
        return await publish_sync(hub.plan_sync.merge(batch))


@app.post("/api/dispatch")
async def dispatch_plan(ref: PlanRef):
    return await hub.dispatch(ref.plan_id)


@app.post("/api/fault")
async def inject_fault(fault: FaultRequest):
    return await hub.inject_fault(fault)


@app.get("/api/report")
async def report():
    post = hub.sim.post
    result = await command_report(post, hub.sim.time)
    if post is not hub.sim.post:
        raise PlanError("report_reset", "Simulation reset during briefing; request a new briefing", 409)
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


@app.post("/api/ask")
async def ask(question: AskQuestion):
    post = hub.sim.post
    result = await command_report(post, hub.sim.time, question=question.question)
    if post is not hub.sim.post:
        raise PlanError("report_reset", "Simulation reset during answer; ask again", 409)
    return result  # private HTTP reply; no screen-wide report broadcast


@app.get("/api/rescue-order")
async def ordered_rescues():
    if os.environ.get("DZ_RESCUE_ORDER") != "1":
        raise PlanError("feature_disabled", "Enable DZ_RESCUE_ORDER=1 for a rescue-order dry run", 409)
    return rescue_order(hub.sim.post, hub.sim.time, hub.sim.prior)


@app.post("/api/control")
async def control(body: dict, request: Request):
    body = {**body, "controller_token": request.headers.get("x-controller-token")}
    await hub.control_message(body)
    return {"ok": True, **hub.control_state()}


@app.websocket("/ws/screen")
async def ws_screen(ws: WebSocket):
    await ws.accept()
    hub.screens.add(ws)
    hub.register_controller(ws, "screen")
    try:
        await ws.send_text(hub.hello(ws))
        await ws.send_text(hub.envelope("maps", hub.sim.maps()))
        await ws.send_text(hub.envelope("tick", hub.sim.snapshot()))
        await ws.send_text(hub.envelope("plan_state", hub.plans.current()))
        while True:
            try:
                msg = json.loads(await ws.receive_text())
                if not isinstance(msg, dict) or not isinstance(msg.get("data"), dict):
                    raise PlanError("invalid_message", "Expected an envelope with object data", 422)
                if msg.get("t") == "control":
                    d = msg["data"]
                    await hub.control_message(d)
                elif msg.get("t") == "lease_override":
                    await hub.change_lease("override", PresenterRelease.model_validate(msg["data"]))
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
        await hub.disconnect_controller(ws)


@app.websocket("/ws/phone")
async def ws_phone(ws: WebSocket,
                   client: str | None = Query(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$"),
                   role: Literal["planner", "relay", "spectator"] = "planner"):
    """Phone planning session; only prior geometry and delivered Command data."""
    await ws.accept()
    if client is None:
        client = f"phone-{hub.next_phone_id}"
        hub.next_phone_id += 1
    hub.phones.add(ws)
    hub.phone_sessions[ws] = client, role
    if role == "planner":
        hub.register_controller(ws, client)
    try:
        if role == "relay":
            hub.attach_relay(client)
        await ws.send_text(hub.envelope("hello", hub.phone_hello(client, role) | hub.controller_hello(ws)))
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


@app.get("/mic-check", include_in_schema=False)
def microphone_check():
    if not hub.leases_enabled():
        raise HTTPException(404)
    return FileResponse(Path(__file__).resolve().parent / "static" / "mic-check.html")


app.mount("/crops", StaticFiles(directory=CROP_DIR), name="crops")

REPO_DIR = Path(__file__).resolve().parents[2]
app.mount("/ai-lab/results", AILabAssets(directory=REPO_DIR / "ml" / "results"), name="ai-lab-results")
app.mount("/ai-lab/slides", AILabAssets(directory=REPO_DIR / "docs" / "assets"), name="ai-lab-slides")


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
