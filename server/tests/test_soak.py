"""Soak test (PLAN.md test_soak): 20 minutes of sim time, 3 robots, no exceptions, memory under
500 MB and flat at the end. Opt-in, because it takes a few minutes:

    DZ_SOAK=1 py -m pytest -q tests/test_soak.py -s          (PowerShell: $env:DZ_SOAK=1)

The run does what the big screen and the director do: builds the tick and map messages the hub
sends (snapshot every tick, maps every 5 ticks, both JSON encoded), and keeps poking the robots:
rubble ahead of a robot, wheel overcurrent, perception overload, a relay switched off and on,
and a baseline / deadzone mode toggle. DZ_SOAK_MINUTES shortens it for a quick check.
"""
import gc
import json
import math
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.robot import perception  # noqa: E402
from deadzone.sim import Sim  # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get("DZ_SOAK") != "1",
                                reason="soak test is opt-in: set DZ_SOAK=1")

MINUTES = float(os.environ.get("DZ_SOAK_MINUTES", "20"))
MAX_RSS_MB = 500
# Command's bundle dedupe table holds ids for one bundle TTL (900 s), so memory may grow until
# then. After it, the only growth allowed is noise.
SETTLED_S = 960
MAX_LATE_GROWTH_MB = 15
MAPS_EVERY = 5


def rss_mb():
    """Resident memory of this process in MB (Windows, Linux, macOS) without psutil."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return pmc.WorkingSetSize / 2**20
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 2**20
    except OSError:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20   # macOS: bytes


def director(sim, t):
    """Keep things happening for the whole run, deterministically."""
    rids = sorted(sim.robots)
    k = int(t)
    if k % 90 == 45:                                   # rubble 1.5 m ahead of a robot
        r = sim.robots[rids[(k // 90) % len(rids)]]
        x, y, th = r.pose
        try:
            sim.drop_rubble((x + math.cos(th) * 1.5, y + math.sin(th) * 1.5))
        except ValueError:
            pass
    if k % 120 == 60:
        sim.inject_overcurrent(rids[(k // 120) % len(rids)], duration_s=1.0)
    if k % 150 == 75:
        sim.robots[rids[(k // 150) % len(rids)]].inject_perception_overload()
    if sim.relays and k % 200 == 100:
        rid = sorted(sim.relays)[(k // 200) % len(sim.relays)]
        sim.set_relay_power(rid, False)
    if sim.relays and k % 200 == 130:
        for rid, relay in sim.relays.items():
            if not relay["on"]:
                sim.set_relay_power(rid, True)
    if k == 600:
        for r in sim.robots.values():
            r.set_mode("baseline")
    if k == 720:
        for r in sim.robots.values():
            r.set_mode("deadzone")


def test_soak_20_minutes():
    perception.reset_detector()
    sim = Sim(n_robots=3, seed=7)
    end = MINUTES * 60
    samples = {}
    last_whole = -1
    events = 0
    t0 = time.perf_counter()
    while sim.time < end - 1e-6:
        whole = int(sim.time)
        if whole != last_whole:
            last_whole = whole
            director(sim, whole)
            if whole % 60 == 0:
                gc.collect()
                samples[whole] = rss_mb()
        sim.tick()
        msg = json.dumps(sim.snapshot(), separators=(",", ":"))
        assert msg
        if sim.tick_n % MAPS_EVERY == 0:
            assert json.dumps(sim.maps(), separators=(",", ":"))
        events += len(sim.drain_events())
    wall = time.perf_counter() - t0
    gc.collect()
    samples[int(end)] = rss_mb()

    speed = end / wall
    print(f"\nsoak: {end:.0f} s of sim in {wall:.0f} s wall ({speed:.1f}x real time), {events} events, "
          f"{len(sim.relays)} relays, RSS by minute: "
          + ", ".join(f"{t // 60}:{mb:.0f}" for t, mb in sorted(samples.items())))
    assert max(samples.values()) < MAX_RSS_MB, f"RSS peaked at {max(samples.values()):.0f} MB"
    late = [mb for t, mb in samples.items() if t >= SETTLED_S]
    if len(late) >= 2:
        assert late[-1] - late[0] < MAX_LATE_GROWTH_MB, f"memory still growing after 16 min: {late}"
    assert all(r.state in ("DONE", "SHUTDOWN", "RETURNING_HOME", "EXPLORING", "REPLANNING", "FAULT",
                           "LOST_LINK_EXPLORING", "RETURNING_TO_SIGNAL", "WAITING_FOR_LINK")
               for r in sim.robots.values())
