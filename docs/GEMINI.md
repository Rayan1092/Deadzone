# Command-only Gemini briefing

The G key already calls `GET /api/report`. This backend can generate the existing
`{text,generated_at,source}` response through real Gemini function calling. Yusuf
owns spoken playback and presentation; text is written to be read aloud. Gemini
never controls robots, edits plans or dispatches anything.

G briefings use at most **3 short sentences and 45 words**, with numbers as
digits (about 15 seconds spoken, depending on the browser voice). The existing
`text` is the concise version; there is no new `short` or `spoken` field. The
server rejects overlong replies or spelled-out numbers and returns an honest
`source:"local"` summary instead of truncating away the final uncertainty.
The local summary counts delivered survivors/routes, reports telemetry age and
the latest historical fault, and states what is unknown. It cannot count people
found only on Reality or infer how many remain unreported.

## Setup for a dry run

Copy `server/.env.example` to **`server/.env`** and set:

```dotenv
GEMINI_API_KEY=your-own-key
DZ_GEMINI=1
```

Restart the backend. It reads `server/.env` regardless of the launch directory;
existing process environment variables take precedence. `.env` is gitignored.
Never put the key in frontend code, a PR, a screenshot or a command-line URL.
`python-dotenv` is included in `server/requirements.txt`.

The default model is `gemini-3.8-flash`, verified against Google's
[Flash model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)
on November 7, 2026. Optional `GEMINI_MODEL` overrides it. The implementation uses
the documented [GenerateContent function-calling API](https://ai.google.dev/gemini-api/docs/generate-content/function-calling).

The toggle defaults off until the testing laptop passes a full dry run. A missing
key, timeout, quota/HTTP error, malformed/blocked reply, unsupported tool or tool
loop returns the deterministic local briefing with **`source:"local"`**. Only an
actual model reply after all six required tools returns **`source:"gemini"`**.
One **10-second deadline** covers the entire multi-turn exchange. HTTP is async,
so the simulation and WebSockets keep running while a report waits.

## Tool boundary

Each request freezes a copy of Command knowledge. The initial prompt contains no
incident state. Gemini obtains facts only through these read-only calls:

| Tool | Evidence |
| --- | --- |
| `get_robots()` | Last delivered robot telemetry and its staleness |
| `get_survivors()` | Delivered survivor reports |
| `get_routes()` | Delivered rescue routes, lengths, clearance and timestamps |
| `get_network()` | Delivered relay announcements, count and recent receipt paths; no live link claims |
| `get_faults()` | Delivered fault history, not live fault flags |
| `get_events(since=0)` | Up to 200 delivered Command events, independent of the drained screen feed |
| `get_coverage()` | Coverage of Command's map only |

All six core tools are required before accepting a briefing. Function responses
retain call IDs and complete model turns retain thought signatures. The model has
no references to Sim, live robot state, live queues/RSSI, hidden survivors, truth
rubble, director events or mutating APIs. Fault records and relay announcements
are explicitly described as historical evidence.

## Phone Ask contract

`POST /api/ask` accepts `{ "question": "where should team 2 go?" }` and returns
the same `{text,generated_at,source}` shape. Questions must be strings of 1-1000
characters and are trimmed; blank questions or unknown fields return 422. It uses
the same opt-in, model, six Command tools, snapshot and total 10-second deadline.
Ask answers keep their question-specific behavior; G's 3-sentence/45-word limit
does not apply to them.
Replies are private HTTP responses; questions and answers are not broadcast to
the screen or other phones. A reset in flight returns 409 `report_reset`.

When unavailable it returns `source:"local"` and explicitly says that the local
Command summary does not answer the question. It never invents an answer. The
phone UI, pending/error state, speech and optional browser question history are
Yusuf's work; no frontend files changed here.

## Validation

Tests use an in-process HTTP mock, never a real API key. They cover parallel and
multi-turn calls, snapshot isolation, unknown tool rejection, hidden-data exclusion,
call IDs/signatures, 10-second total deadline, loop/quota/malformed response
fallback, endpoint broadcasting and simulation progress during API waits.

A real Gemini request and spoken playback still require a keyed testing-laptop
dry run. Confirm `source` in the response; a local fallback is not a Gemini pass.
