# Added scope: backend detection assets, status and rescue delivery

This implements Aziz's part of PLAN.md's Added scope. Yusuf owns the visuals;
Rayan owns route planning, route generation, survivor confirmation and relay
inventory. The rescue contract below follows the team-approved handoff provided
by the user, with the compatibility adjustment for PR #25 described below.

## Detection assets and status

`GET /crops/<file>` serves `ml/crops/runtime/` using a static mount before the web
SPA fallback. The six checked-in positive/negative PNGs are available to detection
cards. Missing images and traversal outside that directory return 404.

Screen and phone `hello.data` add:

```json
{"detector":"model"}
```

or, for fallback:

```json
{"detector":"sim","detector_reason":"DETECTOR=sim"}
```

Status comes from the active cached detector used by robot perception. The fallback
reason is diagnostic text, not a fixed enum. Reset/reconnect hellos include the
same fields. Phone floorplans still omit hidden survivor/decoy locations. Public
crop assets carry no position information; Command detection cards must use only
delivered survivor records, as Yusuf's UI already does.

## Rescue route transport and storage

The robot sends a DTN bundle with `kind:"rescue_route"`, priority 1, `src` equal to
the robot ID and `dst:"CMD"`. Payload:

```json
{
  "survivor_id":"S1",
  "by":"R1",
  "t":182.3,
  "path":[[2,15],[8,15],[36,27]],
  "length_m":46.2,
  "beacon_id":"RL3"
}
```

`beacon_id` is a string or null. Coordinates and `length_m` are meters. `path` has
1–60 finite 2D points within the building bounds; `t` and `length_m` are finite,
nonnegative numbers. `by` must match the source. This illustrative path is not
a claim of a traversable route; Rayan supplies the actual A* result. The backend
validates the wire record, not the truth-map safety of an unknown route.

Routes use normal DTN custody, TTL, shared bandwidth and retries. Byte accounting
includes the JSON payload and envelope, even if the caller supplies a smaller
size estimate. Command learns nothing at enqueue time or an intermediate hop.

On final accepted delivery, Command stores the route and emits:

```json
{"kind":"rescue_route_reported","survivor":"S1","by":"R1",
 "path":[[2,15],[8,15],[36,27]],"length_m":46.2,"beacon_id":"RL3",
 "t":182.3,"reported_t":187.3,"delay_s":5.0}
```

One route per survivor is retained. A strictly newer payload `t` replaces it;
equal timestamps keep the first accepted route. Duplicate bundles and older
routes do not repeat the route event. An older route resent later cannot replace
a newer generation. The route event means a delivered route update, not an
additional survivor detection/report.

Every `tick.command` and phone `cmd_view` includes `routes`, including an empty
list before any delivery. Records have the event fields above without `kind` or `delay_s`.
Late joiners can draw them without replaying events. Reset clears the list.

### PR #25 compatibility and event-name adjustment

PR #25 currently sends `{survivor,by,t,path,length_m,clearance_m,beacon}` instead
of the agreed `{survivor_id,by,t,path,length_m,beacon_id}`. The receive adapter
accepts either wire form and exposes the agreed record with `survivor` and
`beacon_id`. It also retains `beacon` as an equal-value alias and nullable
`clearance_m` so clients built against PR #25's published contract keep working.
Do not send both input aliases in the same bundle.

PR #25's seed-7 S1 route contains 95 sampled points. For legacy input only, the
adapter removes duplicate/strictly collinear forward vertices before applying
the 60-point bound. It preserves endpoints, every corner and every reversal;
it does not invent shortcuts or consult the truth map. If the path still cannot
fit, it is rejected. New canonical senders must send at most 60 points. DTN byte
accounting always uses the actual transmitted payload, not its compacted view.

The delivered event is **`rescue_route_reported`**, because PR #25 already uses
`rescue_route` for the robot's Reality-side computation event. Reusing the name
would mix undelivered and delivered notifications. This is the one intentional
change from the forwarded event contract, and retains PR #25's delivery-event
name plus the agreed route fields and `delay_s`. Command drawing must use
`command.routes`, never a robot's Reality event.

## Beacon IO and metadata

Rayan calls `io.drop_relay(beacon_for="S1")`. It drops at odometry position and
returns the relay ID only while the robot has no route to CMD. While linked it
returns null/None, creates no relay and emits no drop event. Rayan owns the
inventory check/decrement. Existing `io.drop_relay()` still works for ordinary
relay policy while linked.

`relay_dropped` adds `beacon_for` (survivor ID or null). Reality relays have the
same field immediately; Command/phone relay records learn it only from delivered
relay telemetry. Ordinary/phone relays use null. Power/move/reconnect behavior is
unchanged. Beacon announcements include their metadata in byte accounting.

**Route generation/sending must not depend on beacon success.** A linked robot,
or one with no relays left, must still send its route with `beacon_id:null`.
The backend accepts valid route bundles regardless of current radio reachability;
DTN holds them until a route exists.

## Remaining owners

- Rayan: PR #25 currently calls `io.drop_relay()` for beacons. Change that call to
  `io.drop_relay(beacon_for=rec["id"])` to tag the drop event/relay metadata, and
  keep the route at most 60 points. Route planning remains robot-owned. Legacy
  calls still create ordinary relays; the backend does not infer beacon tags.
- Yusuf: Command route drawing and beacon markers; existing detection cards/chip
  can consume the crop endpoint and detector status immediately after merge.
- Aziz: these transport/Command/IO hooks, followed by the separately tracked
  Gemini/FEC/recorder work. No robot policy or frontend source is edited here.
