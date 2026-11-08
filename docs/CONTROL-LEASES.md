# One controller per robot

Enable `DZ_CONTROL_LEASES=1` for a dry run. `DZ_VOICE=1` also enables enforcement;
there is no voice-enabled configuration that bypasses leases. Both default off.
Planning, safety checking and plan dispatch stay shared. Leases govern direct
robot commands, not the shared search plan or simulation disaster injections.

Connect `/ws/phone?client=<id>` as a planner, or `/ws/screen`. Its private first
hello includes `controller_token`, an opaque per-connection bearer. Keep it in
memory; never broadcast it or put it in a URL, recording, localStorage or logs.
A reconnect gets a new token and requires explicit reclaim. The client query ID
is a display identity, not authorization; another tab using that ID cannot take
or release the first connection's robot. Relay and `role=spectator` sockets get no
token and cannot claim. They can view state. All planner phones can still plan.

| Request | JSON body | Authorization |
| --- | --- | --- |
| GET `/api/leases` | none | public state only |
| POST `/api/leases/claim` | `{robot:"R2",name:"Judge 2"}` | `X-Controller-Token` |
| POST `/api/leases/heartbeat` | `{robot:"R2"}` | same holder token |
| POST `/api/leases/release` | `{robot:"R2"}` | same holder token |
| POST `/api/leases/override` | `{robot:"R2",presenter_token:"..."}` | server-configured presenter credential |

Responses and WS envelope `t:"leases"` contain:

```json
{"enabled":true,"ttl_s":15,"revision":4,"server_time":1794096000,
 "robots":[{"robot":"R2","controller":{"client":"judge-2","name":"Judge 2"},"expires_at":1794096015}]}
```

The actual robots array contains every robot; free robots have null controller
and expires_at. Hello also includes `leases`. `server_time` and `expires_at` are
Unix seconds for UI countdowns, with revision monotonically increasing across
reset. Backend expiry uses monotonic **wall time**, independent of pause or sim
speed. Heartbeat every 5 seconds. Release, disconnect, reset or 15 seconds without
heartbeat frees ownership; a heartbeat never reclaims an expired lease. Claim is
atomic: one winner, subsequent contenders get 409 `robot_controlled`. Repeat
claim by the same live token renews it. No ordinary force-take operation exists.

Missing/forged session tokens return 403 `invalid_controller`; a valid session
that does not hold the robot gets 403 `lease_required`. Wrong presenter credential
returns 403 `presenter_required`; unknown robot 404; disabled mutations 409
`feature_disabled`. Normal validation errors are 422. Never treat a timeout or
rejection as ownership or a robot acknowledgement.

Presenter override frees only: it does not transfer ownership, grant a command
bypass, close a phone socket, or renew another controller. Set process-only
`DZ_PRESENTER_TOKEN`; the tunnel launcher generates it in ignored
`.demo/presenter-token.txt` while running. Yusuf's presenter screen can accept it
privately in memory and send `t:"lease_override",data:{robot,presenter_token}`.
Anyone with a public screen URL is **not** automatically a presenter.
Use the presenter screen on `http://127.0.0.1:<port>` on the demo laptop so its
credential stays on loopback; phones use the public HTTPS origin.

Direct REST commands send `X-Controller-Token`; screen control data sends
`controller_token`. Existing director `resume`, new POST `/api/robot-command`
`{robot,action:"resume"}`, and all-robot `mode` all validate ownership immediately
before mutation/enqueue, with no await between them. Mode requires the caller to
hold every targeted robot and rejects atomically if any is missing. Presenter
may release then explicitly claim targets; override itself never sends a command.
Resume still travels as the existing command bundle, without direct robot state
mutation. Already accepted/in-flight bundles are not cancelled by lease release.
Rubble, aftershock, overload/overcurrent injections and global sim start/pause/reset
are disaster/presentation controls, not direct robot driving. Plan dispatch is
explicitly shared, as required.

POST `/api/voice` accepts `{robot,text,request_id?}` with `DZ_VOICE=1`. It rejects
a non-holder before provider work and checks the same grant again immediately
before enqueue, including after safety computation. Missing provider config/failure
returns 503 without a guessed command. Raw audio, typed manual actions and speech
from actually delivered robot acknowledgements are in [VOICE.md](VOICE.md).
Never play a robot reply from the queued response: wait for command_ack_reported.

Yusuf: show controller names, disable taken robots, offer explicit Take/Release,
heartbeat every 5 seconds, and merge state by revision. Do not retain private
controller/presenter credentials in replay recordings. When all robots are taken,
extra phones remain planners/spectators or relays; no phone gets kicked off.
