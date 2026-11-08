# Presenter B/U controls: backend handoff for Yusuf

Aziz's backend is ready for explicit fleet ownership. User requested backend-only
work; no `web/` source is edited here. This does not by itself make the current
big-screen keys work with leases enabled. Keep the fixed demo's voice/leases off
until your UI integration and a joint dry run pass.

## API and session

Connect the existing `/ws/screen`. With `DZ_CONTROL_LEASES=1` (also implied by
`DZ_VOICE=1`), its first private `hello.data` contains `controller_token` and
`leases`. Keep that token only in connection-local memory. Do not copy it into
localStorage, URLs, recordings, logs or broadcast state. A new socket gets a new
token and requires an explicit Take action.

Public lease state has revision, server_time, ttl_s and one entry per robot:

```json
{"enabled":true,"ttl_s":15,"revision":4,"server_time":1794096010,
 "robots":[{"robot":"R1","controller":{"client":"screen","name":"Presenter"},
            "expires_at":1794096025}]}
```

Names and `client:"screen"` are display labels; every screen has a distinct token.
They cannot identify which tab owns a robot. Track the successful local claim
and clear it on loss/release/reset/disconnect; do not infer ownership from a name.
Process state by revision so older responses cannot overwrite newer broadcasts.

## Take / release / heartbeat

Send `X-Controller-Token: <this socket's token>` on every lease request.

| Purpose | POST | Body |
| --- | --- | --- |
| Take the fleet explicitly | `/api/leases/group/claim` | `{"robots":["R1","R2","R3"],"name":"Presenter"}` |
| Renew held targets every 5 seconds | `/api/leases/group/heartbeat` | `{"robots":["R1","R2","R3"]}` |
| Release held targets | `/api/leases/group/release` | `{"robots":["R1","R2","R3"]}` |

Use actual deployed IDs from `hello`, not a hardcoded fleet size. Every list is
nonempty, unique, at most 3 IDs. Every request returns the existing public
`leases` shape and broadcasts it to screens/phones. Existing single-robot
claim/heartbeat/release endpoints still work, including for U's target only.

These group operations validate every target before changing any lease:

- If R3 belongs to a judge, Take fleet returns 409 `robot_controlled`; R1/R2 are
  not partially acquired, and already-held leases are not renewed by the failure.
- Heartbeat fails with 403 `lease_required` if any selected lease is missing,
  expired or owned elsewhere. It does not renew the remaining targets.
- Release permits already-free targets, but returns 403 without releasing any
  owned target if another target belongs to somebody else.
- Unknown robot: 404 `robot_not_found`; invalid/duplicate/empty/extra fields: 422;
  missing/forged controller: 403 `invalid_controller`; feature off: 409
  `feature_disabled`. Never render a failed request as a successful claim.

Expiry uses wall time even when paused. Disconnect and reset free all grants;
heartbeat cannot reclaim them. A reset preserves the connection token, but clears
ownership, so require Take again. Subsequent screen `hello` messages after
reset/rubble may omit the private token: retain it on that same socket only.
Stop renewal after disconnect/release; reconnect must never auto-claim.

## B and U

After confirmed ownership, send existing screen controls with the token inside
`data`. B requires ownership of every deployed robot and rejects atomically if
any target is not owned. U requires only its target's live lease.

```json
{"t":"control","data":{"action":"mode","value":"baseline","controller_token":"<private>"}}
```

```json
{"t":"control","data":{"action":"director","value":{"do":"resume","robot":"R2"},"controller_token":"<private>"}}
```

Use `value:"deadzone"` for the other B state. The REST equivalent is
`POST /api/control` with the same action/value body and `X-Controller-Token`.
Read the returned/broadcast control state; do not optimistically change mode.
U queues a radio command. A `control` response does not prove delivery, robot
resume, or an acknowledgement: continue showing actual telemetry/events.

If a user presses B/U without ownership, show who holds the targets and offer an
explicit Take action. Do not automatically claim or release somebody's robot
from a key press. Disable UI shortcuts while typing, including textarea/select
and contenteditable, and ignore Ctrl/Meta/Alt combinations.

## Presenter release override

The existing override still only frees a robot. It never grants ownership or
sends a command. Accept the presenter credential privately, then send the
existing `lease_override` WS message or `/api/leases/override`. After successful
release, Take is still required, and a competing claimant can win. Never add a
force flag to Take fleet. See [CONTROL-LEASES.md](CONTROL-LEASES.md).

## Recording and acceptance

The current screen socket passes the raw frame to `recordFrame` before parsing.
Your integration must redact `hello.data.controller_token` before recording;
replay must never restore credentials, run heartbeats or send live lease requests.
Presenter credentials stay in memory too. This is a frontend follow-up, not a
backend permission bypass.

Dry run: claim fleet, B both directions, U a SAFE_STOP target, then conflict with
a second phone. Verify no partial fleet claim, visible holder/error, heartbeat
while paused, expiry after lost heartbeat, explicit reclaim after reset/reconnect,
and release-only override. Inspect an exported recording for private tokens.
Backend integration tests cover the admission/atomicity/session paths; physical
browser and phone acceptance remain separate.

Validation for this backend change: **427 passed, 1 opt-in soak skipped** in
119.22 s, including the fixed-demo guard and 14 new group regressions. No web
source was changed, and no current demo service was restarted.
