"""Opt-in paced Hub-loop soak. Run with the project's Python, no server needed."""
import argparse
import asyncio
import json
import math
from functools import lru_cache
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def windows_memory_api():
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    kernel = ctypes.WinDLL("kernel32")
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi")
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    return ctypes, kernel, psapi, Counters


def memory_mb():
    """Current and process lifetime peak resident memory, in decimal MB."""
    if sys.platform == "win32":
        ctypes, kernel, psapi, Counters = windows_memory_api()
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError("Cannot measure process memory")
        return counters.WorkingSetSize / 1e6, counters.PeakWorkingSetSize / 1e6
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mb = peak / (1e6 if sys.platform == "darwin" else 1000)
    status = Path("/proc/self/statm")
    current = int(status.read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6 if status.exists() else peak_mb
    return current, peak_mb


async def run(args):
    # A clean Version 1/default-path soak, independent of a developer's env toggles.
    os.environ.update(DZ_ROBOTS="3", DZ_SEED="7", DZ_SPEED="10", DZ_MODE="deadzone", DZ_AUTOSTART="0",
                      DZ_FEC="0", DZ_GEMINI="0", DZ_CRDT="0", DZ_AFTERSHOCK="0", DZ_RESCUE_ORDER="0",
                      DETECTOR="model")
    sys.path.insert(0, str(ROOT / "server"))
    from deadzone.app import hub
    from deadzone.command.plan import SearchPlan
    from deadzone.robot.perception import get_detector
    detector = get_detector().mode
    if detector != "model":
        raise RuntimeError("Trained detector required for this soak")
    plan = {"plan_id":"SOAK-1", "author":"soak", "lost_link_budget_s":60, "no_go":[], "zones":[
        {"id":"ZW", "robot":"R1", "poly":[[0,17],[20,17],[20,30],[0,30]], "comms":"relay"},
        {"id":"ZNE", "robot":"R2", "poly":[[32,17],[40,17],[40,30],[32,30]], "comms":"lost_link_ok"},
        {"id":"ZB", "robot":"R3", "poly":[[20,17],[32,17],[32,30],[20,30]], "comms":"relay"}]}
    hub.plans.save(SearchPlan.model_validate(plan))
    if not hub.plans.dispatch("SOAK-1")["ok"]:
        raise RuntimeError("Soak demo plan failed safety")
    hub.running, hub.speed = True, 10
    start_sim, started = hub.sim.time, time.perf_counter()
    samples, next_progress = [], 100
    task = asyncio.create_task(hub.loop())
    error = None
    try:
        while hub.sim.time - start_sim < args.duration:
            if task.done():
                task.result()
                raise RuntimeError("Hub loop stopped unexpectedly")
            current, peak = memory_mb()
            elapsed = time.perf_counter() - started
            simulated = hub.sim.time - start_sim
            samples.append({"sim_s":round(simulated,1), "rss_mb":round(current,2), "peak_mb":round(peak,2)})
            if peak >= args.memory_limit_mb:
                raise RuntimeError("Process peak RSS exceeded the memory limit")
            if elapsed > args.duration / 10 * 2 + 30:
                raise RuntimeError("Soak fell too far behind target pace")
            if simulated >= next_progress:
                print(json.dumps({"progress_sim_s":round(simulated,1), "wall_s":round(elapsed,2),
                                  "rss_mb":round(current,2), "peak_mb":round(peak,2)}), flush=True)
                next_progress += 100
            await asyncio.sleep(.1)
    except Exception as failure:
        error = str(failure)
    finally:
        hub.running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as failure:
            error = error or str(failure)
    wall = time.perf_counter() - started
    simulated = hub.sim.time - start_sim
    current, peak = memory_mb()
    warm = next((s["rss_mb"] for s in samples if s["sim_s"] >= min(60, args.duration / 2)), current)
    growth = current - warm
    checks = {"duration_complete": simulated >= args.duration, "no_exceptions": error is None,
              "memory_under_limit": peak < args.memory_limit_mb, "growth_under_limit": growth <= 25,
              "pace_achieved": simulated / wall >= 9.5}
    result = {"ok":all(checks.values()), "checks":checks,
              "seed":7, "robots":3, "detector":detector, "target_speed":10,
              "simulated_s":round(simulated,1), "wall_s":round(wall,2), "actual_speed":round(simulated / wall,3),
              "rss_mb":round(current,2), "peak_rss_mb":round(peak,2), "rss_growth_after_warmup_mb":round(growth,2),
              "memory_limit_mb":args.memory_limit_mb, "growth_limit_mb":25, "min_actual_speed":9.5,
              "survivors_reported":sorted(hub.sim.post.survivors), "bundles_delivered":hub.sim.post.delivered,
              "tick":hub.sim.tick_n, "error":error, "samples":samples}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key:value for key,value in result.items() if key != "samples"}), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=1200, help="simulated seconds, default 1200")
    parser.add_argument("--memory-limit-mb", type=float, default=500)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if (not math.isfinite(arguments.duration) or not math.isfinite(arguments.memory_limit_mb)
            or arguments.duration <= 0 or arguments.memory_limit_mb <= 0):
        parser.error("duration and memory limit must be positive")
    raise SystemExit(asyncio.run(run(arguments)))
