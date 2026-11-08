"""Backpressure must not make newer draft/reset state followed by stale plans."""
import asyncio
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.command.crdt import MergeBatch
from deadzone.command.plan import SearchPlan

api = importlib.import_module("deadzone.app")


def plan(budget=60):
    return SearchPlan.model_validate({"plan_id":"ORDER", "author":"a", "lost_link_budget_s":budget,
        "zones":[{"id":"Z1", "robot":"R1", "poly":[[3,14],[6,14],[6,16],[3,16]]}]})


def batch(epoch, client, budget):
    return MergeBatch.model_validate({"epoch":epoch,"plan_id":"ORDER","ops":[
        {"client":client,"counter":1,"target":"plan","field":"lost_link_budget_s","value":budget}]})


class Sink:
    def __init__(self, hold_kind=None):
        self.messages = []
        self.hold_kind = hold_kind
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.held = False

    async def send_text(self, raw):
        frame = json.loads(raw)
        self.messages.append(frame)  # frame written before transport drain blocks
        if frame["t"] == self.hold_kind and not self.held:
            self.held = True
            self.entered.set()
            await self.release.wait()

    def plans(self):
        return [frame["data"] for frame in self.messages if frame["t"] == "plan_state"]


async def race(first, second, sink):
    a = asyncio.create_task(first())
    await asyncio.wait_for(sink.entered.wait(), 2)
    b = asyncio.create_task(second())
    await asyncio.sleep(0)  # allow the second request to reach mutation/publication
    overtook = b.done()
    sink.release.set()
    await asyncio.wait_for(asyncio.gather(a, b), 2)
    return overtook


def prepare(monkeypatch, hold_kind):
    monkeypatch.setenv("DZ_CRDT", "1")
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    hub = api.Hub()
    monkeypatch.setattr(api, "hub", hub)
    phone, screen = Sink(hold_kind), Sink()
    hub.phones.add(phone)
    hub.phone_sessions[phone] = ("a", "planner")
    hub.screens.add(screen)
    return hub, phone, screen


def test_slow_phone_cannot_publish_old_crdt_state_after_new_merge(monkeypatch):
    async def run():
        hub, phone, screen = prepare(monkeypatch, "plan_sync")
        epoch = hub.plan_sync.seed(plan())["epoch"]
        overtook = await race(lambda: api.merge_sync(batch(epoch,"a",90)),
                              lambda: api.merge_sync(batch(epoch,"b",120)), phone)
        assert not overtook
        assert [p["lost_link_budget_s"] for p in phone.plans()] == [90,120]
        assert [p["lost_link_budget_s"] for p in screen.plans()] == [90,120]
        assert hub.plans.current()["lost_link_budget_s"] == 120
    asyncio.run(run())


def test_slow_phone_cannot_reverse_legacy_plan_updates_on_screen(monkeypatch):
    async def run():
        hub, phone, screen = prepare(monkeypatch, "plan_state")
        overtook = await race(lambda: api.save_plan(plan(90),check=False),
                              lambda: api.save_plan(plan(120),check=False), phone)
        assert not overtook
        assert [p["lost_link_budget_s"] for p in screen.plans()] == [90,120]
        assert hub.plans.current()["lost_link_budget_s"] == 120
    asyncio.run(run())


def test_reset_cannot_be_followed_by_old_inflight_plan_publication(monkeypatch):
    async def run():
        hub, phone, screen = prepare(monkeypatch, "plan_sync")
        epoch = hub.plan_sync.seed(plan())["epoch"]
        lock = hub.plan_lock
        overtook = await race(lambda: api.merge_sync(batch(epoch,"a",90)),
                              lambda: hub.control("reset"), phone)
        assert not overtook
        # Phone reset is a fresh hello with plan:null; screens receive plan_state:null.
        drafts = [frame["data"].get("plan") if frame["t"] == "hello" else frame["data"]
                  for frame in phone.messages if frame["t"] in ("hello", "plan_state")]
        assert drafts[-1] is None and screen.plans()[-1] is None
        assert hub.plans.current() is None and not hub.plan_sync.docs
        assert hub.plan_lock is lock
        assert hub.sim.tick_n == 1 and not hub.running
    asyncio.run(run())
