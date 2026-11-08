# Final-stretch backend contract

Rayan's next list was relayed by the user. G shortening is merged in #89; the
remaining backend additions extend #90. The presenter UI and J/I data panels
require Yusuf's integration/agreement. Rayan announces the freeze. No web, robot
policy, ML or map source is modified by these additions.

## G and presenter B/U

G retains `{text,generated_at,source}` and Command-only facts, at most 3 sentences
and 45 words, numbers as digits. Nonconforming model output falls back honestly
to local text; Ask remains question-specific. #89 is already merged and has no
review comments; its protocol/privacy/length tests are rerun with this work.

The explicit group claim/heartbeat/release API and existing token on B/U are in
[PRESENTER-LEASE-HANDOFF.md](PRESENTER-LEASE-HANDOFF.md). Existing UI still needs
that handoff. Keep leases/voice off for the fixed demo until joint acceptance.

## Earthquake strength

With `DZ_AFTERSHOCK=1`, send the existing director control over screen WS or
`POST /api/control`:

```json
{"action":"director","value":{"do":"aftershock","strength":"strong"}}
```

`strength` is `normal` (default, original one-area behavior) or `strong`. Optional
`at` and `relay` keep their existing validation. Strong creates 2 distinct
collapse areas now and queues a third for +10 **simulation** seconds; pause stops
that delay. At most 2 available ordinary relays are destroyed, and only their
custody is lost. With fewer than 2 available relays, the number destroyed is the
number actually available; none are invented. A new strong request while its
secondary collapse is pending returns 422 without further mutation.

Each area emits existing `aftershock`/`rubble_fall`/`relay_destroyed` events and
updates actual truth geometry/radio. Robot maps and Command change only through
normal sensing/delivery. The Hub publishes a fresh screen hello when delayed
geometry changes occur, so rendered walls match the new geometry. Reset clears
pending collapses. The fixed demo uses no strong quake unless explicitly chosen.

## Reset into a floorplan and timeline

`GET /api/scenarios` returns `{floorplans:[{id,name}],selected,timeline_enabled,
timeline_available}`. It lists local registered files beneath `data/floorplans/`;
no survivor counts, coordinates or disaster schedule are exposed by this API.
Examples: `collapse_01`, `generated/gen_1`. No arbitrary file paths or uploads.
Startup `DZ_FLOORPLAN` accepts one of those IDs or its repo-relative JSON path;
unset keeps `collapse_01`. Startup never automatically plays a timeline.

One existing control selects the map and resets the incident:

```json
{"action":"reset","value":{"floorplan":"generated/gen_1","timeline":true}}
```

New selection/script validation completes before the live world is replaced.
Unknown ID is 404; malformed map/script is 422; a missing feature gate is 409.
Reset leaves the simulation paused after its existing initial sensor/delivery
tick and clears plans, CRDT epochs, leases, voice state, counters, relays and
pending disasters. Connected controller identities survive but need explicit
reclaim. Screen/phone hello/maps refresh for the new dimensions. Phone hello still
uses only the public planning prior, without survivors, rubble or timeline.

Plain reset keeps the selected map and timeline setting; `value:{timeline:false}`
disables scripts. `DZ_SCENARIO_TIMELINE=1` is required to enable scripts. If the
script contains an aftershock, `DZ_AFTERSHOCK=1` is also required. Timeline events
are finite times from 0 to 86400 sim seconds, with at most 256 events; supported
actions are the generator's `rubble`, `overcurrent`, `aftershock`. All event fields,
positions and robot IDs validate before reset. Equal times keep original order.
Events run once on simulation ticks, never wall timers. Reset restarts the script.
If an intervening manual action makes an event unavailable (for example a strong
quake is already pending), emit one Reality-only `timeline_event_failed`, count
the failure, and continue the loop instead of silently claiming success or retrying.

## Under the hood: screen tick.stats

Existing `robots`, `relays`, `links_up`, `delivered`, `in_flight` remain. Additions
reset with the incident; snapshot calls do not increment work. They are diagnostic
screen data, never phone `cmd_view`, Command knowledge or Gemini tools.

| Keys | Meaning |
| --- | --- |
| `ticks`, `sim_s` | Actual simulation frames and simulation seconds. |
| `lidar_scans`, `lidar_rays`, `thermal_scans`, `thermal_hits`, `drive_calls` | Actual RobotIO calls, rays returned and thermal hits returned; hits include rejected hot spots when the model is active. |
| `survivor_detections`, `hotspots_rejected`, `rescue_routes_computed`, `replans`, `faults_raised` | Cumulative robot events. Multiple robots can detect the same survivor; these are event counts, not unique survivor totals. |
| `survivors_reported`, `rescue_routes_delivered` | Current unique delivered Command survivors/routes. |
| `bundles_created` | Unique source-owned bundle IDs first seen by transport, including separate peer unicast copies. |
| `hop_transfers`, `transport_delivered` | Accepted per-hop custody transfers and final deliveries to all destinations, including peer robots. Existing `delivered` remains the Command accepted-bundle count. |
| `bytes_transmitted` | Cumulative simulated hop bytes, including parity, partial/interrupted attempts and retries; bandwidth is continuous, so this can be fractional. Not measured physical traffic. |
| `bundles_expired`, `bundles_evicted`, `bundles_destroyed`, `custody_refusals` | Actual TTL expiries, storage evictions, destroyed custody and rejected completed custody attempts. |
| `corrupted_bytes`, `corrected_bytes`, `fec_failed_blocks` | Lifetime sums of actual seeded channel/RS results. Per-link values still describe only the latest transport tick. |
| `queued_bytes`, `relays_destroyed` | Current stored bundle-byte estimates and physically destroyed relay count. |
| `deadline_misses`, `safety_deadline_misses` | Cumulative actual scheduler miss counters; these include the scheduler's skipped-release policy. |
| `exploration_searches` | V2 explorer graph-search counter; 0 with V2 disabled. This is not a count of every A* call. |
| `aftershock_areas` | Actual collapse areas applied, including delayed ones. |
| `timeline_events_played`, `timeline_events_failed`, `timeline_events_total` | Successful, failed and scheduled script events. |

## Judge test assets and conditional J/I panels

`/ai-lab/results/judge_pool/<file>` already maps to `ml/results/judge_pool/<file>`
through the gated read-only `AILabAssets` mount. It supports nested JSON/images,
GET/HEAD, `Cache-Control:no-cache`, and rejects writes, hidden files, model weights
and paths outside the ML results root. `DZ_AI_LAB=1` is required even for cached
requests. Files exported after startup are immediately available; an absent
pool/manifest/image returns 404. No placeholder dataset, fabricated judge score,
or new inference API is created here. The actual pool is not present in this
checkout yet; Rayan owns that export.

Yusuf can build I from tick.stats and J from the exported pool contract. The user
said Aziz can implement those web data panels if Yusuf agrees. Until agreement
is recorded, the current backend-only boundary applies. Physical browser/GPU,
keyed Gemini/ElevenLabs and two-phone acceptance remain distinct from automated
backend tests. The separate paced 10x soak remains a performance task, not a pass
implied by these counters or tests.
