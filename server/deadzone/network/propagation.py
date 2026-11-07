"""Multi-wall indoor path loss model and link graph with hysteresis.

P_rx = P_tx - L0 - 10 n log10(d / d0) - sum(wall losses crossed)
"""
import math

import numpy as np

from ..geometry import count_crossings

L0_DB = 40.0          # loss at d0 = 1 m, 2.4 GHz
PATH_EXP = 2.6        # cluttered collapse
LINK_UP_DBM = -82.0   # link comes up above this
LINK_DOWN_DBM = -88.0  # link goes down below this
NOISE_DBM = -95.0


def rssi(fp, p, q, tx_dbm=20.0):
    d = max(math.dist(p, q), 1.0)
    walls = count_crossings(p, q, fp.segs)
    loss = L0_DB + 10 * PATH_EXP * math.log10(d) + float(fp.seg_loss[walls].sum())
    return tx_dbm - loss


def throughput_bps(r):
    """Bytes per second a link can move at this RSSI. Linear 250 kB/s at -60 to 20 kB/s at -88."""
    if r >= -60:
        return 250_000
    if r <= LINK_DOWN_DBM:
        return 20_000
    f = (r - LINK_DOWN_DBM) / (-60 - LINK_DOWN_DBM)
    return 20_000 + f * 230_000


class LinkGraph:
    """Keeps link up/down state per node pair so links don't flap at the threshold."""

    def __init__(self):
        self.up = {}
        self.rssi = {}

    def update(self, fp, nodes):
        """nodes: dict id -> (x, y, tx_dbm, on). Returns list of (a, b, became_up | became_down | None)."""
        changes = []
        ids = sorted(nodes)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                pa, pb = nodes[a], nodes[b]
                key = (a, b)
                if not (pa[3] and pb[3]):
                    r = -200.0
                else:
                    r = rssi(fp, pa[:2], pb[:2], min(pa[2], pb[2]))
                self.rssi[key] = r
                was = self.up.get(key, False)
                now = r > LINK_UP_DBM if not was else r > LINK_DOWN_DBM
                self.up[key] = now
                if now != was:
                    changes.append((a, b, "up" if now else "down"))
        return changes

    def neighbors(self, n):
        out = []
        for (a, b), u in self.up.items():
            if u and (a == n or b == n):
                out.append((b if a == n else a, self.rssi[(a, b)]))
        return out

    def path(self, src, dst, avoid=()):
        """Cheapest Dijkstra path, excluding prior custodians in ``avoid``.

        Cost = 1 + max(0, (-60 - rssi) / 10). Returns node ids or None.
        """
        import heapq
        dist = {src: 0.0}
        prev = {}
        pq = [(0.0, src)]
        while pq:
            d, n = heapq.heappop(pq)
            if n == dst:
                out = [dst]
                while out[-1] != src:
                    out.append(prev[out[-1]])
                return out[::-1]
            if d > dist.get(n, 1e18):
                continue
            for m, r in self.neighbors(n):
                if m in avoid:
                    continue
                nd = d + 1 + max(0.0, (-60 - r) / 10)
                if nd < dist.get(m, 1e18):
                    dist[m] = nd
                    prev[m] = n
                    heapq.heappush(pq, (nd, m))
        return None

    def link_rssi(self, a, b):
        key = (a, b) if a < b else (b, a)
        return self.rssi.get(key, -200.0)

    def as_list(self, min_rssi=-100.0):
        out = []
        for (a, b), r in self.rssi.items():
            if r > min_rssi or self.up.get((a, b)):
                out.append({"a": a, "b": b, "rssi": round(r, 1), "up": self.up.get((a, b), False),
                            "fec": bool(self.up.get((a, b)) and r < -80)})
        return out


def coverage_map(fp, src, tx=20.0, step=1.0):
    """RSSI grid (for tuning and tests) at step meter resolution."""
    xs = np.arange(step / 2, fp.W, step)
    ys = np.arange(step / 2, fp.H, step)
    out = np.zeros((len(ys), len(xs)))
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            out[j, i] = rssi(fp, src, (x, y), tx)
    return out
