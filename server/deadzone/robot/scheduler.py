"""Fixed-priority preemptive (rate monotonic) scheduler, simulated at 1 ms inside each 100 ms tick.

Each robot runs these tasks on its onboard computer. The sim tick is one 100 ms frame. We
simulate the frame at 1 ms resolution and report the execution slices so the big screen can
draw a task timeline. A preempted job shows up as several slices with the same name. Jobs that
do not finish in a frame carry over to the next one.

Contract (robot telemetry `tasks`): list of {name, start, dur, missed}, start and dur in
virtual ms within the frame (0 to 100), missed = the job behind that slice is past its deadline.

Overrun policy: if a task's previous job is still unfinished when the next one is released, the
new release is skipped and counted as a miss (bounded queue, like a real frame-skip policy).
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


class Job:
    __slots__ = ("prio", "name", "left", "deadline", "missed")

    def __init__(self, prio, name, wcet, deadline):
        self.prio, self.name, self.left, self.deadline, self.missed = prio, name, wcet, deadline, False


class Scheduler:
    def __init__(self, tasks=TASKS):
        self.tasks = list(tasks)
        self.cycle = hyperperiod_frames(self.tasks)   # 1000 ms = 10 frames for the plan table
        self.wcet = {name: c for name, _, c in self.tasks}
        self.jobs = []                 # unfinished jobs carried between frames
        self.misses = {name: 0 for name in NAMES}
        self.new_misses = []           # task names that missed a deadline in the last frame
        self._cache = {}

    def set_wcet(self, name, ms):
        self.wcet[name] = int(ms)

    def reset_wcet(self, name):
        self.wcet[name] = next(c for n, _, c in self.tasks if n == name)

    def nominal(self):
        return all(self.wcet[n] == c for n, _, c in self.tasks)

    def run_frame(self, frame):
        """Slices for frame number `frame`. A clean nominal frame (nothing carried over, plan
        WCETs) repeats every hyperperiod, so it is cached. Treat the result as read-only."""
        if not self.jobs and self.nominal():
            key = frame % self.cycle
            if key not in self._cache:
                slices, left = self._simulate(key)
                if left:                     # cannot happen at U = 0.377, but stay correct
                    self.jobs = left
                    return slices
                self._cache[key] = slices
            self.new_misses = []
            return self._cache[key]
        slices, self.jobs = self._simulate(frame, self.jobs)
        return slices

    def _simulate(self, frame, carried=()):
        t0 = frame * FRAME_MS
        jobs = list(carried)
        slices, last = [], None
        self.new_misses = []
        for ms in range(FRAME_MS):
            now = t0 + ms
            for prio, (name, period, _) in enumerate(self.tasks):
                if now % period:
                    continue
                if any(j.name == name for j in jobs):
                    self._miss(name)          # previous job overran: skip this release
                    continue
                jobs.append(Job(prio, name, self.wcet[name], now + period))
            for j in jobs:
                if not j.missed and now >= j.deadline:
                    j.missed = True
                    self._miss(j.name)
            if not jobs:
                last = None
                continue
            job = min(jobs, key=lambda j: (j.prio, j.deadline))
            job.left -= 1
            if last is job:
                slices[-1]["dur"] += 1
                slices[-1]["missed"] = slices[-1]["missed"] or job.missed
            else:
                slices.append({"name": job.name, "start": ms, "dur": 1, "missed": job.missed})
            last = job
            if job.left <= 0:
                jobs.remove(job)
                last = None
        return slices, jobs

    def _miss(self, name):
        self.misses[name] += 1
        self.new_misses.append(name)
