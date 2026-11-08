# Opt-in aftershock director

Set `DZ_AFTERSHOCK=1` before an aftershock dry run. Send to `/api/control` or the
screen `control` message:

```json
{"action":"director","value":{"do":"aftershock","at":[22,15],"relay":"RL1"}}
```

Both `at` and `relay` are optional. Defaults: first powered non-phone relay and its
position, or `[22,15]` on the demo floorplan when none exists. Explicit bad positions
or unknown/already destroyed relays fail before mutation. Disabled feature returns
409 `feature_disabled`; invalid scenario returns 422 `invalid_aftershock`.

The event adds a clipped 2m rubble area and a 3m concrete wall at its north edge.
Truth occupancy and radio loss update immediately. Destroyed relays have
`destroyed:true,on:false`; they cannot be powered/moved/reconnected into service.
Their custody queue and partial transfers are lost. Other custodians retain their
bundles and the normal router finds surviving paths. Reset clears all damage.

Screen-only events:

- `aftershock {at,rubble:[{id,poly,height,dynamic}],walls:[{id,a,b,material,dynamic}],destroyed_relay,lost_bundles}`
- `relay_destroyed {id,pos,lost_bundles}`
- Existing `rubble_fall` and link up/down events.

The screen gets a hello refresh for the geometry and an immediate tick/maps update.
New walls are in **`hello.floorplan.dynamic_walls`**, separate from public `walls`.
Yusuf: wire key **A** for this director action and draw those walls in Reality only.
The pure Command inset continues using public walls and delivered occupancy.

Phones receive neither director events nor truth geometry. Command map/relay
knowledge does not change directly; later delivered lidar/map/telemetry can teach
it about the aftermath. Gemini sees the same delivered Command boundary. Robot
behavior remains Rayan-owned and reacts only through normal lidar/collision/radio
IO. `Sim.aftershock(at=None,relay=None)` is the backend scenario hook.

Tests cover atomic validation, permanent destruction, custody loss versus retained
bundles, alternate-route delivery, truth/prior/Command separation, feature gating
and reset. The testing-laptop dry run and Yusuf's key/geometry wiring remain pending.
