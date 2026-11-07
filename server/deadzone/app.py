"""FastAPI app: runs the sim loop and streams state to the big screen and phones.

Run:  uvicorn deadzone.app:app --host 0.0.0.0 --port 8000
"""
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .sim import DT, Sim

MAPS_EVERY = 5
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


class Hub:
    def __init__(self):
        self.sim = Sim(n_robots=int(os.environ.get("DZ_ROBOTS", "1")), seed=int(os.environ.get("DZ_SEED", "7")))
        self.running = False
        self.speed = float(os.environ.get("DZ_SPEED", "2"))
        self.screens: set[WebSocket] = set()
        self.phones: set[WebSocket] = set()
        self.seq = 0

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

    async def broadcast_tick(self):
        snap = self.sim.snapshot()
        await self.send_all(self.screens, self.envelope("tick", snap))
        if self.sim.tick_n % MAPS_EVERY == 0:
            await self.send_all(self.screens, self.envelope("maps", self.sim.maps()))
            await self.send_all(self.phones, self.envelope("cmd_view", snap["command"]))
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
            await self.send_all(self.screens, self.hello())
            await self.send_all(self.screens, self.envelope("maps", self.sim.maps()))
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
    yield
    task.cancel()


app = FastAPI(title="Deadzone sim", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"ok": True, "tick": hub.sim.tick_n, "time": hub.sim.time, "running": hub.running}


@app.get("/api/floorplan")
def floorplan():
    return JSONResponse(hub.sim.fp.data)


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
async def ws_phone(ws: WebSocket):
    """Stub for Person 3: phones only ever see the Command view."""
    await ws.accept()
    hub.phones.add(ws)
    await ws.send_text(hub.envelope("hello", hub.sim.hello()))
    await ws.send_text(hub.envelope("cmd_view", hub.sim.snapshot()["command"]))
    try:
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.phones.discard(ws)


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
