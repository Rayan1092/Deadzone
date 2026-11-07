"""Deterministic local briefing, using delivered Command knowledge only.

This is the fallback/report endpoint contract, not a Gemini implementation.
"""


def local_report(post, now):
    view = post.view(now)
    lines = [f"Command briefing at T+{now:.1f}s."]
    for robot in sorted(view["robots"], key=lambda r: r["id"]):
        lines.append(f"{robot['id']}: {robot['state']}, reported battery {robot['battery_pct']:.0f}%, "
                     f"last report {robot['stale_s']:.1f}s old.")
    if not view["robots"]:
        lines.append("No robot telemetry has reached Command.")
    found = sorted(s["id"] for s in view["survivors"])
    lines.append("Reported survivors: " + (", ".join(found) if found else "none") + ".")
    lines.append(f"Announced relays: {len(view['relays'])}; bundles delivered: {post.delivered}.")
    for fault in view["faults"]:
        lines.append(f"Reported fault: {fault['robot']} {fault['fault']}.")
    return {"text": "\n".join(lines), "generated_at": now, "source": "local"}
