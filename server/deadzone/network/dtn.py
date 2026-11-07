"""Delay-tolerant bundles.

1:30-5:00 milestone: single hop store and forward. A node keeps every bundle in its
outbox until the link graph has a path to the destination, then hands bundles over
in priority order, limited by link throughput. The receiver taking the bundle is the
custody transfer, so a bundle is never in two places and never lost.

Person 2 extends this at 5:00 PM: per-hop forwarding through relays, custody acks,
dedupe by bid, TTL expiry, relay queues.
"""
import itertools

PRIO = {"survivor": 0, "fault": 1, "command": 1, "plan": 1, "telemetry": 2, "map_patch": 3}
_seq = itertools.count(1)


def make_bundle(src, dst, kind, payload, created, size, ttl=900.0):
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


def drain_outbox(outbox, budget_bytes, now):
    """Pop bundles in (priority, age) order until the byte budget is spent.

    Returns the delivered bundles. Expired bundles are dropped.
    """
    outbox[:] = [b for b in outbox if now - b["created"] <= b["ttl"]]
    outbox.sort(key=lambda b: (b["prio"], b["created"]))
    sent = []
    while outbox and (budget_bytes >= outbox[0]["size"] or not sent):
        b = outbox.pop(0)
        budget_bytes -= b["size"]
        sent.append(b)
        if budget_bytes <= 0:
            break
    return sent
