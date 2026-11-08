# Phone rescue order

Enable `DZ_RESCUE_ORDER=1` for a dry run and call `GET /api/rescue-order`.
The response is `{generated_at,source:"command",survivors:[...]}`; each survivor has
`{survivor,by,length_m,risk,reasons,reported_t}`. The list joins delivered survivor
records to the latest delivered rescue route. A survivor without a delivered route,
or a route without a delivered survivor report, is omitted.

This is a route-risk heuristic for the simulated exercise, not medical triage or a
safety guarantee. Data may be stale; it does not command responders or robots.
Sort is low, medium, high risk, then route length, then survivor ID.

| Risk/reason code | Evidence |
| --- | --- |
| high / `reported_route_obstructed` | A sampled route cell is occupied in the delivered Command map |
| high / `known_hazard_on_route` | Sampled route intersects the public pre-collapse hazard grid |
| high / `very_low_clearance` | Delivered route clearance <0.25 m |
| medium / `narrow_clearance` | Delivered clearance <0.5 m |
| medium / `clearance_unknown` | Route did not report clearance |
| medium / `route_older_than_60s` | Source route time is over 60 sim seconds old |
| low / no reasons | None of the above evidence is present |

Every segment is sampled at most half a grid cell apart. This is a discretized
heuristic, not a continuous geometry proof. Truth occupancy, live relay power,
current robot pose/faults, hidden survivors and undelivered routes are never read.
Existing Command routes are not edited or recomputed. Disabled endpoint returns
409 `feature_disabled`; no tick/phone envelope change is needed.

Yusuf owns the phone list and reason labels. Actual phone/testing-laptop dry run
remains pending; endpoint and no-leak behavior have backend test coverage.
