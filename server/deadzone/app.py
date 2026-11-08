"""FastAPI app: runs the sim loop and streams state to the big screen and phones.

Run:  uvicorn deadzone.app:app --host 0.0.0.0 --port 8000
"""
import asyncio
import base64
from copy import deepcopy
import hashlib
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
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .ai_lab import AILabAssets
from .command.plan import EpochPlanRef, PlanDraft, PlanError, PlanManager, PlanRef, SearchPlan
from .command.crdt import MergeBatch, PlanSync
from .command.leases import LeaseClaim, LeaseGroupClaim, LeaseTable, PresenterRelease, RobotGroup, RobotRef
from .command import voice as voice_services
from .command.voice import ManualCommand, SpeechRequest, VoiceRequest
from .command.controls import AskQuestion, FaultRequest, RelayPlace, RelayPower, director_adapter
from .command.reports import command_report
from .command.rescue_order import rescue_order
from .command.frames import FrameUpload, MAX_BODY_BYTES, PhoneFrames
from .command.safety import SafetyChecker
from .robot.robot import resume_command
from .robot.perception import CROP_DIR, get_detector
from .sim import DT, ROBOT_DEFS, Sim
from .lan import lan_ipv4
from .public_text import PublicText
from .network.dtn import make_bundle
from .network.stream import StreamState, compact_message, stream_profile, thin_tick
from .network.map_delta import DRAWN_LIDAR_POINTS, MapDeltaState
from .network.lite import LiteScreen
from .web_assets import ProductionFiles
from .scenarios import ResetScenario, prepare_scenario, scenario_catalog

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


def phone_join_url(base_url="http://localhost:8000", peer=None):
    configured = os.environ.get("DZ_PUBLIC_URL")
    try:
        parts = urlsplit(configured or base_url)
        port = parts.port
    except ValueError:
        raise HTTPException(503, "Set DZ_PUBLIC_URL to a valid HTTP(S) frontend origin") from None
    if (parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password
            or (configured and (parts.path not in ("", "/") or parts.query or parts.fragment))):
        raise HTTPException(503, "Set DZ_PUBLIC_URL to the public HTTP(S) frontend address")
    local_host = parts.hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "::")
    local_host |= parts.hostname.endswith((".localhost", ".local")) or "." not in parts.hostname
    try:
        local_host |= ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        pass
    if local_host:
        address = lan_ipv4(peer)
        if address is None:
            raise HTTPException(503, "Connect the laptop to Wi-Fi or use the HTTPS tunnel; no LAN address is available")
        parts = parts._replace(netloc=f"{address}:{port or (443 if parts.scheme == 'https' else 80)}")
    url = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") + "/phone", "", ""))
    return url


def public_links():
    if not os.environ.get("DZ_PUBLIC_URL"):
        return {}
    try:
        phone = phone_join_url()
    except HTTPException:
        return {}  # /api/join reports invalid configuration; never advertise a bad URL.
    return {"public_url": phone.removesuffix("/phone"), "phone_url": phone}


class Hub:
    def __init__(self):
        count = int(os.environ.get("DZ_ROBOTS", "1"))
        self.scenario_id, path, player = prepare_scenario(os.environ.get("DZ_FLOORPLAN") or "collapse_01",
                                                         [rid for rid, _, _ in ROBOT_DEFS[:count]])
        self.timeline_enabled = False
        self.sim = Sim(plan_path=path, n_robots=count, seed=int(os.environ.get("DZ_SEED", "7")))
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
        self.stream = StreamState(enabled=os.environ.get("DZ_STREAM_OPTIMIZE") == "1")
        self.compact_clients = set()
        self.compact_stream = os.environ.get("DZ_COMPACT_STREAM", "1") == "1"
        self.delta_screens = {}
        self.lite_screens = {}
        self.plan_lock = asyncio.Lock()  # survives reset: old publications finish first
        self.lease_lock = asyncio.Lock()
        self.leases = LeaseTable(self.sim.robots)
        self.controller_sockets = {}
        self._init_plans()

    def _init_plans(self):
        self.stream.reset()
        self.plan_epoch = secrets.token_hex(16)
        for state in self.delta_screens.values():
            state.reset(self.plan_epoch)
        checker = SafetyChecker(self.sim.prior, self.sim.robot_specs, self.sim.energy_time_scale)
        self.plans = PlanManager(self.sim, checker)
        self.plan_sync = PlanSync(self.plans)
        self.command_requests = {}
        self.speech_cache = {}
        self.phone_frames = PhoneFrames(os.environ.get("DZ_PHONE_FRAMES") == "1", self.plan_epoch)
        self.public_text = PublicText({r.id: r.name for r in self.sim.robots.values()},
                                      self.sim.prior.data.get("rooms", []), self.plans.saved)

    def envelope(self, t, data):
        self.seq += 1
        display = data if t in {"maps", "map_patch", "plan_state", "leases", "relay_state"} else self.public_text.payload(data)
        return json.dumps({"t": t, "seq": self.seq, "time": self.sim.time, "data": display},
                          separators=(",", ":"))

    async def send_all(self, clients, msg, *, force_tick=False):
        dead = []
        compact = {}
        for ws in list(clients):
            try:
                wire = msg
                if ws in self.lite_screens:
                    wire = self.lite_screens[ws].transform(wire, initial=force_tick)
                    if wire is None:
                        continue
                if ws in self.delta_screens:
                    wire = self.delta_screens[ws].transform(wire)
                    if wire is None:
                        continue
                elif ws in self.compact_clients:
                    profile = ws in self.lite_screens
                    if profile not in compact:
                        compact[profile] = compact_message(wire)
                    wire = compact[profile]
                await ws.send_text(wire)
            except Exception:
                dead.append(ws)
        for ws in dead:
            clients.discard(ws)
            self.compact_clients.discard(ws)
            self.delta_screens.pop(ws, None)
            self.lite_screens.pop(ws, None)

    async def send_one(self, ws, msg):
        if ws in self.lite_screens:
            msg = self.lite_screens[ws].transform(msg, initial=True)
        if ws in self.delta_screens:
            msg = self.delta_screens[ws].transform(msg)
        elif ws in self.compact_clients:
            msg = compact_message(msg)
        if msg is not None:
            await ws.send_text(msg)

    async def accept_socket(self, ws, compact=False):
        await ws.accept()
        if compact and not self.stream.enabled:
            await ws.close(code=1008, reason="Compact stream is disabled")
            return False
        if compact:
            self.compact_clients.add(ws)
        return True

    def screen_snapshot(self):
        snapshot = self.sim.snapshot()
        if self.compact_stream and not self.stream.enabled:
            return thin_tick(snapshot, DRAWN_LIDAR_POINTS)
        return thin_tick(snapshot) if self.stream.enabled else snapshot

    def screen_maps(self):
        return self.stream.maps(self.sim.maps())

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

    async def change_lease_group(self, action, body, token):
        self.require_leases()
        async with self.lease_lock:
            if self.leases.expire():
                await self.broadcast_leases()
            self.leases.group(action, body.robots, token, getattr(body, "name", None))
            await self.broadcast_leases()
            return self.lease_state()

    def authorize_robot(self, robot, token):
        if self.leases_enabled():
            self.leases.require(robot, token)

    def require_voice(self):
        if os.environ.get("DZ_VOICE") != "1":
            raise PlanError("feature_disabled", "Enable DZ_VOICE=1 for voice control", 409)

    def live_grant(self, robot, token, post, grant):
        if post is not self.sim.post:
            raise PlanError("voice_reset", "Simulation reset during command; submit a new request", 409)
        self.leases.require(robot, token)
        if self.leases.leases[robot] is not grant:
            raise PlanError("lease_changed", "Control was released or reclaimed; submit a new request", 409)

    async def issue_command(self, robot, token, *, intent=None, text=None, audio=None, mime=None, request_id=None):
        self.require_leases()
        self.leases.require(robot, token)
        is_voice = intent is None
        # Only spoken input needs the voice services (transcription, Gemini). A phone button
        # (hold, resume, return home, explore a zone) is built and safety-checked locally, so
        # control leases alone are enough: the phone shows these buttons whenever leases are on.
        if is_voice:
            self.require_voice()
        post, grant = self.sim.post, self.leases.leases[robot]
        book = self.command_requests
        key = token, request_id or secrets.token_hex(16)
        fingerprint = hashlib.sha256(json.dumps({"robot":robot,"text":text,"mime":mime,
            "audio":hashlib.sha256(audio).hexdigest() if audio is not None else None,
            "intent":intent.model_dump(mode="json") if intent is not None else None},sort_keys=True).encode()).hexdigest()
        for old in list(book):
            if book[old]["result"] is not None and book[old]["expires"] <= time.monotonic():
                del book[old]
        if key in book:
            entry = book[key]
            if entry["fingerprint"] != fingerprint:
                raise PlanError("request_conflict", "Use a new request_id for different input", 409)
            if entry["result"] is None:
                raise PlanError("request_in_progress", "This request is processing; retry the same ID later", 409)
            return deepcopy(entry["result"])
        if len(book) >= 256 or any(k[0] == token and e["robot"] == robot and e["result"] is None for k,e in book.items()):
            raise PlanError("command_busy", "Command processing is busy; retry later with the same request_id", 429)
        entry = {"robot":robot,"fingerprint":fingerprint,"result":None,"expires":0}
        book[key] = entry
        try:
            stt_source, intent_source = "manual", "manual"
            if is_voice:
                stt_source, intent_source = "browser", "gemini"
                if audio is not None:
                    text = await voice_services.transcribe(audio, mime)
                    stt_source = "elevenlabs"
                    self.live_grant(robot, token, post, grant)
                rooms = [{k:r[k] for k in ("id","name")} for r in self.sim.prior.data.get("rooms", [])]
                intent = await voice_services.parse_intent(text, rooms)
            async with self.plan_lock:
                self.live_grant(robot, token, post, grant)
                draft = self.plans.current()
                if draft and intent.action not in ("hold", "resume"):
                    self.plan_sync.assert_valid(draft["plan_id"])
                cmd_id = "V-" + secrets.token_hex(16)
                command, safety = voice_services.command_and_safety(
                    self.sim.prior, self.plans, post, self.sim.time, robot, intent, cmd_id, self.leases.actor(token))
                # Checking a large room can take time: recheck expiry after safety too.
                self.live_grant(robot, token, post, grant)
                now = self.sim.time
                result = {"queued":safety["ok"], "cmd_id":cmd_id if safety["ok"] else None,
                          "robot":robot,"action":intent.action,"command":command,"transcript":text,
                          "stt_source":stt_source,"intent_source":intent_source,"safety":safety,
                          "status":"waiting_for_robot" if safety["ok"] else "refused","issued_t":now}
                if safety["ok"]:
                    payload = {**command,"cmd_id":cmd_id,"source":"voice" if is_voice else "phone",
                               "by":self.leases.actor(token),"issued_t":now}
                    size = len(json.dumps(payload,separators=(",",":")).encode()) + 64
                    self.sim.network.queues["CMD"].append(make_bundle("CMD",robot,"command",payload,now,size))
                else:
                    result["say"] = "Command safety check refused: " + "; ".join(v["msg"] for v in safety["violations"])
                entry["result"], entry["expires"] = deepcopy(result), time.monotonic()+300
                return result
        finally:
            if entry["result"] is None:
                book.pop(key, None)

    async def delivered_speech(self, cmd_id):
        self.require_voice()
        post = self.sim.post
        ack = deepcopy(post.command_acks.get(cmd_id))
        if ack is None:
            raise PlanError("ack_not_delivered", "No delivered acknowledgement for this command", 404)
        cache = self.speech_cache
        key = cmd_id, ack["status"], ack["t"]
        if key not in cache:
            while len(cache) >= 32:
                evict = next((k for k,e in cache.items() if e["result"] is not None), None)
                if evict is None:
                    raise PlanError("speech_busy", "Speech requests are busy; retry later", 429)
                del cache[evict]
            cache[key] = {"lock":asyncio.Lock(),"result":None}
        entry = cache[key]
        async with entry["lock"]:
            if post is not self.sim.post:
                raise PlanError("voice_reset", "Simulation reset during speech", 409)
            if entry["result"] is None:
                result = await voice_services.speech(self.public_text.payload(ack))
                if post is not self.sim.post:
                    raise PlanError("voice_reset", "Simulation reset during speech", 409)
                entry["result"] = result
            return deepcopy(entry["result"])

    def hello(self, ws=None):
        return self.envelope("hello", self.sim.hello() | self.control_state()
                             | ({"stream": stream_profile()} if self.stream.enabled else {})
                             | {"scenario": {"id": self.scenario_id, "timeline": self.timeline_enabled}}
                             | detector_status() | {"leases": self.lease_state(), "voice":{"enabled":os.environ.get("DZ_VOICE") == "1"}}
                             | self.controller_hello(ws) | self.phone_frames.capabilities() | public_links())

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
                "plan_epoch": self.plan_epoch, "dispatched_plan_ids": sorted(self.plans.dispatched),
                "relay_id": self.relay_clients.get(client) if role == "relay" else None,
                "leases": self.lease_state(),
                "voice": {"enabled":os.environ.get("DZ_VOICE") == "1"},
                **({"stream": stream_profile()} if self.stream.enabled else {}),
                **self.phone_frames.capabilities(),
                **detector_status(), **public_links()}

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
                    await self.send_one(ws, self.envelope("relay_state", self.relay_state(client)))
                except (RuntimeError, WebSocketDisconnect):
                    await self.disconnect_phone(ws, notify=False)

    async def disconnect_phone(self, ws, notify=True):
        session = self.phone_sessions.pop(ws, None)
        self.phones.discard(ws)
        self.compact_clients.discard(ws)
        await self.disconnect_controller(ws)
        if session is not None:
            client, role = session
            if role == "relay" and client in self.relay_clients and (client, role) not in self.phone_sessions.values():
                self.sim.set_relay_power(self.relay_clients[client], False)
                if notify:
                    await self.relay_states()
                    await self.publish_paused_relay_view()

    async def publish_paused_relay_view(self):
        if not self.running:
            await self.send_all(self.screens, self.envelope("tick", self.screen_snapshot()), force_tick=True)

    async def plan_state(self, state):
        message = self.envelope("plan_state", state)
        await self.send_all(self.phones, message)
        await self.send_all(self.screens, message)

    async def save_plan(self, plan, check=True):
        async with self.plan_lock:
            self.require_plan_epoch(getattr(plan, "plan_epoch", None))
            # A plan without zones (no-go only, or empty = clear the exclusions) is accepted: robots keep
            # their current zones (PlanManager.assignments). Rayan's P0, 2026-11-08; edit authorized by Rayan.
            state = self.plans.save(plan)
            self.plan_sync.invalidate(plan.plan_id)
            await self.plan_state(state)
            if check:
                return await self._check_plan(plan.plan_id)
            return {"saved": True, "plan_id": plan.plan_id, "checked": False}

    def require_plan_epoch(self, epoch):
        if epoch is not None and epoch != self.plan_epoch:
            raise PlanError("plan_reset", "The incident reset; reconnect before editing this plan", 409)

    async def dispatch(self, plan_id, epoch=None):
        async with self.plan_lock:
            self.require_plan_epoch(epoch)
            return await self._dispatch(plan_id)

    async def _dispatch(self, plan_id):
        self.plan_sync.assert_valid(plan_id)
        was_dispatched = plan_id in self.plans.dispatched
        result = self.plans.dispatch(plan_id)
        if result["ok"]:
            await self.plan_state(self.plans.get(plan_id).model_dump(mode="json"))
            if not was_dispatched:
                event = self.envelope("event", {"kind": "plan_dispatched", "plan_id": plan_id})
                await self.send_all(self.screens, event)
                await self.send_all(self.phones, event)
        else:
            await self.send_all(self.phones, self.envelope("safety", result))
            await self.send_all(self.screens, self.envelope("event", {"kind": "safety_reject", **result}))
        return result

    def phone_view(self):
        # Do not call snapshot() here: phones need no Reality objects at all.
        view = self.sim.post.view(self.sim.time)
        if self.phone_frames.enabled:
            for robot in view["robots"]:
                if self.phone_frames.linked(self.sim.post, robot["id"], self.sim.time):
                    frame = self.phone_frames.view(robot["id"], self.sim.time)
                    if frame is not None:
                        robot["phone_frame"] = frame
        return view | {
            "map": base64.b64encode(self.sim.post.map.tobytes()).decode()} | self.sim.post.coverage()

    def receive_frame(self, rid, body):
        if not self.phone_frames.enabled:
            raise PlanError("feature_disabled", "Phone frames are disabled", 404)
        if rid not in self.sim.robots:
            raise PlanError("robot_not_found", "Unknown robot", 404)
        if not self.phone_frames.linked(self.sim.post, rid, self.sim.time):
            raise PlanError("frame_no_signal", "Command has no fresh report from this robot", 409)
        return self.phone_frames.accept(rid, body, self.sim.time)

    async def check_plan(self, plan_id, epoch=None):
        async with self.plan_lock:
            self.require_plan_epoch(epoch)
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
            await self.publish_paused_relay_view()
            return
        if role != "planner":
            raise PlanError("read_only_role", "Relay sessions cannot edit or submit search plans", 403)
        if kind == "plan_edit":
            plan = PlanDraft.model_validate({**data, "author": client})
            await self.save_plan(plan, check=False)
        elif kind == "plan_submit":
            ref = PlanRef.model_validate(data)
            await self.check_plan(ref.plan_id)
        else:
            raise PlanError("unsupported_message", f"Unsupported phone message: {kind}", 422)

    async def broadcast_tick(self, force_maps=False):
        if self.stream.tick_due(force_maps):
            await self.send_all(self.screens, self.envelope("tick", self.screen_snapshot()), force_tick=force_maps)
        if force_maps or self.sim.tick_n % MAPS_EVERY == 0:
            maps = self.screen_maps()
            if self.stream.maps_due(maps, force_maps):
                await self.send_all(self.screens, self.envelope("maps", maps))
            await self.send_all(self.phones, self.envelope("cmd_view", self.phone_view()))
            await self.relay_states()
        for ev in self.sim.drain_events():
            message = self.envelope("event", ev)
            await self.send_all(self.screens, message)
            if ev.get("kind") == "command_ack_reported":
                await self.send_all(self.phones, message)

    async def reset(self, selection=None):
        choice = ResetScenario.model_validate(selection or {})
        async with self.plan_lock:
            async with self.lease_lock:
                timeline = self.timeline_enabled if choice.timeline is None else choice.timeline
                if timeline and os.environ.get("DZ_SCENARIO_TIMELINE") != "1":
                    raise PlanError("feature_disabled", "Enable DZ_SCENARIO_TIMELINE=1 for disaster scripts", 409)
                identifier, path, player = prepare_scenario(choice.floorplan or self.scenario_id,
                    self.sim.robots, timeline, allow_aftershock=os.environ.get("DZ_AFTERSHOCK") == "1")
                # Prepare the new world before swapping it. Invalid selection/script leaves the old incident intact.
                candidate = Sim(plan_path=path, n_robots=self.sim.n_robots, seed=self.sim.seed)
                candidate.timeline = player if timeline else None
                candidate.tick()
                self.running = False
                self.sim = candidate
                self.scenario_id, self.timeline_enabled = identifier, timeline
                self._init_plans()
                self.leases.reset()
                await self.broadcast_leases()
            self.relay_clients.clear()
            self.relay_power_requests.clear()
            for client, role in sorted(set(self.phone_sessions.values())):
                if role == "relay":
                    self.attach_relay(client)
            await self.send_all(self.screens, self.hello())
            await self.send_all(self.screens, self.envelope("maps", self.screen_maps()))
            await self.send_all(self.screens, self.envelope("plan_state", None))
            for ws, (client, role) in list(self.phone_sessions.items()):
                try:
                    await self.send_one(ws, self.envelope("hello", self.phone_hello(client, role) | self.controller_hello(ws)))
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
        if data.get("action") == "rubble" and "robot" in data:
            # {t:"control", data:{action:"rubble", robot:"R2"}}: the robot id sits next to action (Rayan's contract)
            value = {**(value if isinstance(value, dict) else {}), "robot": data["robot"]}
        await self.control(data.get("action"), value, controller_token=data.get("controller_token"))

    async def control(self, action, value=None, *, controller_token=None):
        if action == "start":
            self.running = True
        elif action == "pause":
            self.running = False
        elif action == "toggle":
            self.running = not self.running
        elif action == "reset":
            if value is not None and not isinstance(value, dict):
                raise PlanError("invalid_reset", "Reset value must be a scenario object", 422)
            await self.reset(value)
            return
        elif action == "rubble":
            # The R key on the followed robot: {action:"rubble", robot:"R2"}; no robot means R1.
            # With DZ_SMART_RUBBLE=1 the rubble lands on that robot's path ahead, never trapping anyone.
            robot = (value or {}).get("robot") if isinstance(value, dict) else None
            robot = robot or "R1"
            if robot not in self.sim.robots:
                raise PlanError("robot_not_found", f"Unknown robot: {robot}", 404)
            self.sim.press_rubble(None, robot=robot)
            await self.send_all(self.screens, self.hello())
            await self.broadcast_tick(force_maps=True)
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
                    self.sim.earthquake(request.strength, request.at, request.relay)
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
            placed = self.sim.press_rubble(fault.at, fault.size)   # DZ_SMART_RUBBLE=1 may move it onto the path
            await self.send_all(self.screens, self.hello())
            result = {"ok": True, "type": "rubble", "at": placed["at"], "smart": placed["smart"]}
        await self.broadcast_tick()
        return result

    async def loop(self):
        next_t = time.perf_counter()
        while True:
            await self.sweep_leases()
            if self.running:
                revision = self.sim.geometry_revision
                self.sim.tick()
                changed = revision != self.sim.geometry_revision
                if changed:
                    await self.send_all(self.screens, self.hello())
                await self.broadcast_tick(force_maps=changed)
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


class PublicJSONResponse(JSONResponse):
    def render(self, content):
        return super().render(hub.public_text.payload(content))


app = FastAPI(title="Deadzone sim", lifespan=lifespan, default_response_class=PublicJSONResponse)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)


def validation_issues(error):
    # Do not echo arbitrary input, NaN or non-serializable validator contexts.
    friendly = {"missing": "Complete the missing value and try again.",
                "extra_forbidden": "This update contains an unsupported setting.",
                "string_pattern_mismatch": "This name contains unsupported characters.",
                "json_invalid": "The update could not be read. Please try again."}
    return [{"loc": list(issue["loc"]), "msg": friendly.get(issue["type"], issue["msg"])} for issue in error.errors()]


@app.exception_handler(PlanError)
async def plan_error(request, error):
    return PublicJSONResponse(status_code=error.status, content={"detail": {"code": error.code, "msg": str(error)}})


@app.exception_handler(RequestValidationError)
async def request_error(request, error):
    return PublicJSONResponse(status_code=422, content={"detail": {"code": "invalid_request",
                        "msg": "Request validation failed", "issues": validation_issues(error)}})


@app.exception_handler(ValidationError)
async def control_validation_error(request, error):
    return await request_error(request, error)


@app.exception_handler(StarletteHTTPException)
async def http_error(request, error):
    detail = {404: "This page or resource is unavailable.", 405: "This action is unavailable on this page."}.get(error.status_code, error.detail)
    return PublicJSONResponse(status_code=error.status_code, content={"detail": detail}, headers=error.headers)


@app.post("/api/frames/{robot_id}")
async def upload_frame(robot_id: str, request: Request):
    if not hub.phone_frames.enabled:
        raise PlanError("feature_disabled", "Phone frames are disabled", 404)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BODY_BYTES:
            raise PlanError("frame_size", "Frame request is too large", 413)
    body = FrameUpload.model_validate_json(bytes(raw))
    async with hub.plan_lock:
        result = hub.receive_frame(robot_id, body)
        # Also deliver while paused, without advancing the sim or reading Reality.
        await hub.send_all(hub.phones, hub.envelope("cmd_view", hub.phone_view()))
        return result


@app.get("/api/health")
def health():
    return {"ok": True, "tick": hub.sim.tick_n, "time": hub.sim.time, "running": hub.running}


@app.get("/api/scenarios")
def scenarios():
    return {"floorplans": scenario_catalog(), "selected": hub.scenario_id,
            "timeline_enabled": hub.timeline_enabled,
            "timeline_available": os.environ.get("DZ_SCENARIO_TIMELINE") == "1"}


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


@app.post("/api/leases/group/claim")
async def claim_lease_group(body: LeaseGroupClaim, request: Request):
    return await hub.change_lease_group("claim", body, request.headers.get("x-controller-token"))


@app.post("/api/leases/group/heartbeat")
async def heartbeat_lease_group(body: RobotGroup, request: Request):
    return await hub.change_lease_group("heartbeat", body, request.headers.get("x-controller-token"))


@app.post("/api/leases/group/release")
async def release_lease_group(body: RobotGroup, request: Request):
    return await hub.change_lease_group("release", body, request.headers.get("x-controller-token"))


@app.post("/api/robot-command")
async def robot_command(body: ManualCommand, request: Request):
    return await hub.issue_command(body.robot,request.headers.get("x-controller-token"),
                                   intent=body,request_id=body.request_id)


@app.post("/api/voice")
async def voice(body: VoiceRequest, request: Request):
    return await hub.issue_command(body.robot,request.headers.get("x-controller-token"),
                                   text=body.text,request_id=body.request_id)


@app.post("/api/voice/audio")
async def voice_audio(request: Request, robot: str, request_id: str | None = None):
    ref = VoiceRequest(robot=robot,text="audio",request_id=request_id)
    hub.require_leases()
    hub.leases.require(robot,request.headers.get("x-controller-token"))
    hub.require_voice()
    post, grant = hub.sim.post, hub.leases.leases[robot]
    mime = request.headers.get("content-type", "").split(";",1)[0].lower().strip()
    if mime not in voice_services.AUDIO_TYPES:
        raise PlanError("unsupported_audio", "Send raw WebM, MP4, WAV, OGG or MPEG audio", 415)
    audio = bytearray()
    async for chunk in request.stream():
        if len(audio) + len(chunk) > voice_services.MAX_AUDIO:
            raise PlanError("audio_too_large", "Recording exceeds 2 MiB", 413)
        audio.extend(chunk)
    if not audio:
        raise PlanError("empty_audio", "Recording is empty", 422)
    hub.live_grant(robot,request.headers.get("x-controller-token"),post,grant)
    return await hub.issue_command(robot,request.headers.get("x-controller-token"),
                                   audio=bytes(audio),mime=mime,request_id=ref.request_id)


@app.post("/api/voice/tts")
async def voice_speech(body: SpeechRequest):
    return await hub.delivered_speech(body.cmd_id)


@app.get("/api/floorplan")
def floorplan():
    return JSONResponse(hub.sim.prior.planning_data())


@app.post("/api/plan")
async def save_plan(plan: PlanDraft, check: bool = True):
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


@app.post("/api/plan/check")
async def check_saved_plan(ref: EpochPlanRef):
    return await hub.check_plan(ref.plan_id, ref.plan_epoch)


@app.post("/api/dispatch")
async def dispatch_plan(ref: EpochPlanRef):
    return await hub.dispatch(ref.plan_id, ref.plan_epoch)


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
    return {"url": phone_join_url(str(request.base_url), request.client.host if request.client else None)}


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
async def ws_screen(ws: WebSocket, compact: bool = False, map_deltas: bool = False, lite: str | None = None):
    if not await hub.accept_socket(ws, compact):
        return
    hub.screens.add(ws)
    if lite is not None and lite.lower() not in ("0", "false"):
        hub.lite_screens[ws] = LiteScreen()
    if map_deltas and hub.compact_stream:
        hub.delta_screens[ws] = MapDeltaState(hub.plan_epoch)
    hub.register_controller(ws, "screen")
    try:
        await hub.send_one(ws, hub.hello(ws))
        await hub.send_one(ws, hub.envelope("maps", hub.screen_maps()))
        await hub.send_one(ws, hub.envelope("tick", hub.screen_snapshot()))
        await hub.send_one(ws, hub.envelope("plan_state", hub.plans.current()))
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
                await hub.send_one(ws, hub.envelope("error", data))
    except (WebSocketDisconnect, RuntimeError, json.JSONDecodeError):
        pass
    finally:
        hub.screens.discard(ws)
        hub.compact_clients.discard(ws)
        hub.delta_screens.pop(ws, None)
        hub.lite_screens.pop(ws, None)
        await hub.disconnect_controller(ws)


@app.websocket("/ws/phone")
async def ws_phone(ws: WebSocket,
                   client: str | None = Query(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$"),
                   role: Literal["planner", "relay", "spectator"] = "planner", compact: bool = False):
    """Phone planning session; only prior geometry and delivered Command data."""
    if not await hub.accept_socket(ws, compact):
        return
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
        await hub.send_one(ws, hub.envelope("hello", hub.phone_hello(client, role) | hub.controller_hello(ws)))
        await hub.send_one(ws, hub.envelope("cmd_view", hub.phone_view()))
        if role == "relay":
            await hub.send_one(ws, hub.envelope("relay_state", hub.relay_state(client)))
            await hub.publish_paused_relay_view()
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
                await hub.send_one(ws, hub.envelope("error", data))
    except PlanError as error:
        await hub.send_one(ws, hub.envelope("error", {"code": error.code, "msg": str(error)}))
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
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


@app.get("/mic-check", include_in_schema=False)
def microphone_check():
    if not hub.leases_enabled() and os.environ.get("DZ_MIC_CHECK") != "1":
        raise HTTPException(404)
    return FileResponse(Path(__file__).resolve().parent / "static" / "mic-check.html")


app.mount("/crops", StaticFiles(directory=CROP_DIR), name="crops")

REPO_DIR = Path(__file__).resolve().parents[2]
app.mount("/ai-lab/results", AILabAssets(directory=REPO_DIR / "ml" / "results"), name="ai-lab-results")
app.mount("/ai-lab/slides", AILabAssets(directory=REPO_DIR / "docs" / "assets"), name="ai-lab-slides")


if WEB_DIST.exists():
    app.mount("/", ProductionFiles(directory=WEB_DIST, html=True), name="web")
