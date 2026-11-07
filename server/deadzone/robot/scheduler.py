"""Fixed-priority preemptive (rate monotonic) scheduler, simulated at 1 ms inside each 100 ms tick.

Each robot runs these tasks on its onboard computer. The sim tick is one 100 ms frame. We
simulate the frame at 1 ms resolution and report the execution slices so the big screen can
draw a task timeline. A preempted job shows up as several slices with the same name.

Contract (robot telemetry `tasks`): list of {name, start, dur, missed}, start and dur in
virtual ms within the frame (0 to 100), missed = that job overran its deadline.
"""
import math

FRAME_MS = 100

# name, period ms, WCET ms. Rate monotonic: shorter period = higher priority (list order).
TASKS = [
    ("safety", 50, 2),
    ("motion", 100, 8),
    ("comms", 200, 10),
    ("mapping", 200, 25),
    ("perception", 500, 40),
    ("battery", 1000, 2),
]
NAMES = [t[0] for t in TASKS]


def utilization(tasks=TASKS):
    return sum(c / p for _, p, c in tasks)


def liu_layland_bound(n=len(TASKS)):
    return n * (2 ** (1 / n) - 1)


def hyperperiod_frames(tasks=TASKS):
    lcm = 1
    for _, p, _ in tasks:
        lcm = lcm * p // math.gcd(lcm, p)
    return max(1, lcm // FRAME_MS)


class Scheduler:
    def __init__(self, tasks=TASKS):
        self.tasks = list(tasks)
        self.cycle = hyperperiod_frames(self.tasks)   # 1000 ms = 10 frames for the plan table
        self._cache = {}

    def run_frame(self, frame):
        """Slices for frame number `frame`. With no overrun nothing carries over between frames,
        so the schedule repeats every hyperperiod and is cached (treat the result as read-only)."""
        key = frame % self.cycle
        if key not in self._cache:
            self._cache[key] = self._simulate(key)
        return self._cache[key]

    def _simulate(self, frame):
        """Simulate frame number `frame` (global time frame*100 ms) at 1 ms resolution."""
        t0 = frame * FRAME_MS
        jobs = []      # [priority, name, remaining, deadline_ms]
        slices = []
        for ms in range(FRAME_MS):
            now = t0 + ms
            for prio, (name, period, wcet) in enumerate(self.tasks):
                if now % period == 0:
                    jobs.append([prio, name, wcet, now + period])
            ready = [j for j in jobs if j[2] > 0]
            if not ready:
                continue
            job = min(ready, key=lambda j: (j[0], j[3]))
            job[2] -= 1
            missed = now + 1 > job[3]
            if slices and slices[-1]["name"] == job[1] and slices[-1]["start"] + slices[-1]["dur"] == ms \
                    and slices[-1]["_job"] is job:
                slices[-1]["dur"] += 1
                slices[-1]["missed"] = slices[-1]["missed"] or missed
            else:
                slices.append({"name": job[1], "start": ms, "dur": 1, "missed": missed, "_job": job})
        return [{k: v for k, v in s.items() if k != "_job"} for s in slices]
