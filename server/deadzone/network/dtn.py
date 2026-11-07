"""Deterministic, bandwidth-limited store and forward with per-hop custody.

A hop is acknowledged atomically after the receiver stores the complete bundle.
Until then the sender retains custody. An interrupted hop restarts on reconnect;
ack packets themselves have no simulated latency or loss yet.
"""
import itertools
import json
from copy import deepcopy

from .propagation import throughput_bps

PRIO = {"survivor": 0, "fault": 1, "command": 1, "plan": 1, "rescue_route": 1,
        "telemetry": 2, "map_patch": 3}
RELAY_QUEUE_BYTES = 2_000_000
_seq = itertools.count(1)


def make_bundle(src, dst, kind, payload, created, size, ttl=900.0):
    if kind == "rescue_route":
        size = max(size, len(json.dumps(payload, separators=(",", ":")).encode()) + 64)
    return {
        "bid": f"{src}-{next(_seq):06d}",
        "src": src,
        "dst": dst,
        "kind": kind,
        "prio": PRIO[kind],
        "created": created,
        "ttl": ttl,
        "custodian": src,
        "hops": [src],
        "size": int(size),
        "payload": payload,
    }


def _order(bundle):
    return bundle["prio"], bundle["created"], bundle["bid"]


class DTNNetwork:
    def __init__(self):
        self.queues = {}
        self.limits = {}
        self._seen = {}       # receiver -> bid -> expiry, including forwarded bundles
        self._delivered = {}  # bid -> expiry (destination dedupe)
        self._progress = {}   # (sender, receiver, bid) -> bytes transmitted
        self.non_forwarding = set()

    def register(self, node, outbox=None, capacity_bytes=None, can_forward=True):
        """Attach an existing robot outbox, or create a relay/command queue."""
        if node in self.queues:
            raise ValueError(f"Node already registered: {node}")
        self.queues[node] = [] if outbox is None else outbox
        self.limits[node] = capacity_bytes
        self._seen[node] = {}
        if not can_forward:
            self.non_forwarding.add(node)

    def _expire(self, now):
        for node, queue in self.queues.items():
            bids = set()
            kept = []
            for b in queue:
                if now <= b["created"] + b["ttl"] and b["bid"] not in bids:
                    kept.append(b)
                    bids.add(b["bid"])
            queue[:] = kept
            self._seen[node] = {bid: expiry for bid, expiry in self._seen[node].items()
                                if now <= expiry}
        self._delivered = {bid: expiry for bid, expiry in self._delivered.items() if now <= expiry}

    def fanout_telemetry(self, bundle, destinations, ttl):
        """Queue source-owned unicast copies; never deliver by inspecting links.

        A recipient suffix makes bids distinct from the CMD report and from each
        other, while repeated fanout of the same report remains idempotent.
        """
        src = bundle["src"]
        recipients = sorted(set(destinations) - {src, bundle["dst"]})
        if bundle["kind"] != "telemetry" or bundle["custodian"] != src or bundle["hops"] != [src]:
            raise ValueError("Only source-owned telemetry can be fanned out")
        if src not in self.queues or any(dst not in self.queues for dst in recipients):
            raise ValueError("Telemetry source and recipients must be registered")
        # Robot telemetry used to have a fixed 120-byte estimate. Account for
        # variable targets/relay lists on both the CMD report and peer copies.
        bundle["size"] = max(bundle["size"], len(json.dumps(bundle["payload"], separators=(",", ":")).encode()) + 64)
        queued = {b["bid"] for b in self.queues[src]}
        for dst in recipients:
            bid = f"{bundle['bid']}/{dst}"
            if bid in queued or bid in self._seen[src]:
                continue
            self.queues[src].append(dict(bundle, bid=bid, dst=dst,
                ttl=min(bundle["ttl"], ttl), hops=[src], payload=deepcopy(bundle["payload"])))
            queued.add(bid)

    def _accept(self, node, bundle):
        """Return a custody ack only after storage, or for an already stored bid."""
        bid = bundle["bid"]
        queue = self.queues[node]
        if bid in self._seen[node] or any(b["bid"] == bid for b in queue):
            return True
        limit = self.limits[node]
        evict = []
        if limit is not None:
            needed = sum(b["size"] for b in queue) + bundle["size"] - limit
            # Prefer life-critical reports, then older bundles. Reject without
            # touching the receiver if even eviction cannot make enough space.
            for b in sorted(queue, key=_order, reverse=True):
                if needed <= 0 or _order(b) <= _order(bundle):
                    break
                evict.append(b["bid"])
                needed -= b["size"]
            if needed > 0:
                return False
        if evict:
            queue[:] = [b for b in queue if b["bid"] not in evict]
            for dropped in evict:
                self._seen[node].pop(dropped, None)
        received = dict(bundle, custodian=node, hops=[*bundle["hops"], node])
        queue.append(received)
        self._seen[node][bid] = bundle["created"] + bundle["ttl"]
        return True

    def step(self, links, dt, now):
        """Advance transfers and return bundles that arrived at their destination.

        Only queues present at tick start may transmit: every hop takes at least
        one tick. Both directions share one byte budget per physical link. A route
        must exist at tick start; a relay retains custody if that route later dies.
        """
        self._expire(now)  # expiry must also run while completely disconnected
        candidates = [(node, b) for node in sorted(self.queues) for b in self.queues[node]]
        candidates.sort(key=lambda item: (*_order(item[1]), item[0]))
        budgets, progress, routes = {}, {}, {}
        for sender, bundle in candidates:
            if bundle["dst"] == sender:
                continue
            if not any(b is bundle for b in self.queues[sender]):
                continue  # another transfer may have evicted this queued bundle
            # Do not revisit a previous custodian, whose receipt would otherwise
            # acknowledge a copy it already forwarded. Wait for a loop-free route.
            avoid = set(bundle["hops"][:-1]) | (self.non_forwarding - {sender, bundle["dst"]})
            route_key = sender, bundle["dst"], tuple(sorted(avoid))
            if route_key not in routes:
                routes[route_key] = links.path(sender, bundle["dst"], avoid=route_key[2])
            path = routes[route_key]
            if not path or len(path) < 2 or path[1] not in self.queues:
                continue
            receiver = path[1]
            edge = tuple(sorted((sender, receiver)))
            if edge not in budgets:
                budgets[edge] = throughput_bps(links.link_rssi(*edge)) * dt
            if budgets[edge] <= 0:
                continue
            key = sender, receiver, bundle["bid"]
            sent = self._progress.get(key, 0.0)
            amount = min(bundle["size"] - sent, budgets[edge])
            sent += amount
            budgets[edge] -= amount
            if sent + 1e-9 < bundle["size"]:
                progress[key] = sent
                continue
            if self._accept(receiver, bundle):
                # The receiver's successful custody ack is the ONLY place a
                # transmitted bundle is removed from the sender's outbox.
                self.queues[sender][:] = [b for b in self.queues[sender]
                                         if b["bid"] != bundle["bid"]]
                self._seen[sender][bundle["bid"]] = bundle["created"] + bundle["ttl"]
        self._progress = progress  # drop partial hops interrupted by link/route changes
        delivered = []
        for node, queue in self.queues.items():
            for b in queue:
                if b["dst"] == node and b["bid"] not in self._delivered:
                    self._delivered[b["bid"]] = b["created"] + b["ttl"]
                    delivered.append(b)
            queue[:] = [b for b in queue if b["dst"] != node]
        return delivered
