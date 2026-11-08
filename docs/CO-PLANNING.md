# Opt-in offline co-planning

Set `DZ_CRDT=1` for a dry run. The backend is a per-field LWW-map CRDT: the greater
`(counter,client)` pair wins. Polygons and requirements objects are atomic values;
region deletions are tombstones, cleared only by an explicit newer `deleted:false`.
It merges draft data only; no check or dispatch runs automatically.

1. Explicitly seed once with `PUT /api/plan-sync`, body a normal SearchPlan. It
   returns `{epoch,plan,ops,valid,issues}`. PUT starts a **new epoch**, invalidating
   old offline clients. Do not PUT automatically on reconnect.
2. `GET /api/plan-sync?plan_id=P-1` returns the merge state. Persist this state and
   pending local ops in the phone browser (Yusuf's UI work).
3. While offline, queue operations and apply them locally. Persist a monotonic
   logical counter; advance it above every observed counter before a new local
   edit. Do not use wall-clock time. Each browser needs its own stable client ID.
4. Reconnect: GET state, merge pending registers by `(counter,client)`, and POST
   `{epoch,plan_id,ops}` to `/api/plan-sync`. Replaying identical ops is safe.

Example operation:

```json
{"client":"phone-a","counter":12,"target":"zone:ZNE","field":"comms","value":"lost_link_ok"}
```

Targets are `plan`, `zone:<id>`, `no_go:<id>`. Plan fields: `lost_link_budget_s`.
Zone fields: `robot,poly,priority,comms,requires,deleted`. No-go fields:
`poly,reason,deleted`. IDs and individual field values follow the normal plan
schema. Region creation needs a complete valid candidate; send its fields together
or show the intermediate invalid state. Author stays the seed plan author; client
stamps identify editing sessions, not authenticated people.

The server broadcasts `plan_sync` to planner phones. Valid candidates also save and
broadcast ordinary `plan_state` to phones/screens. Invalid whole-plan candidates
(e.g. both phones delete the last zones) **still converge** and return `valid:false`
with issues, but do not replace the last valid saved plan. Checks and dispatch are
blocked with 409 `plan_conflict` until fixed, preventing dispatch of an old draft.
Clients must merge incoming winning registers with pending local edits; do not
blindly overwrite pending edits with `plan_state`.

Reset or whole-plan REST/legacy `plan_edit` replacement invalidates the epoch.
409 `sync_epoch` means fetch the replacement and ask the responder to rebase their
pending edits; do not silently recreate the old incident. Dispatched IDs are
immutable. Reusing an identical client/counter/field for different values returns
409 `sync_clock`. Invalid individual operations return 422 without changing state.
GET before seeding returns 404 `sync_not_started`.

Limits: counters 1..2^53-1, 256 ops per batch, 1024 winning registers per plan.
GET `ops` is the compact set of winning registers, not a growing event log.
Phone offline storage, reconnect UI and an actual two-phone dry run remain Yusuf's
work. Existing whole-plan clients continue working when the toggle is off.
