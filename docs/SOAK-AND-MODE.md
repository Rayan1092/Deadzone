# Live comparison control and soak runner

The baseline Q&A control delegates to Rayan's `Robot.set_mode` for all robots:

```json
{"action":"mode","value":"baseline"}
```

Send it to `POST /api/control`, or wrap it as
`{t:"control",data:{action:"mode",value:"baseline"}}` on the screen WebSocket.
Rayan's requested `{action:"mode",mode:"baseline"}` shape also works through
either transport. Existing `value` callers stay supported. Supplying both fields
is accepted only when they agree; conflicting values return 422 `invalid_mode`
(screen `error`) before any robot changes.
Use `value:"deadzone"` to switch back. Invalid values return 422 `invalid_mode`
before changing any robot. The default is unchanged; initial/reset mode follows
`DZ_MODE`. This is an explicit experiment control, never an AI/responder command.

Screen `hello`, `control` and REST control replies add `mode`. It is `baseline` or
`deadzone` for the normal all-robot control; diagnostic `mixed` is possible if
backend code manually switches individual robots. Yusuf owns the key/chip and
`WAITING_FOR_LINK` label. No frontend source was edited here.

Rayan owns Gemini key creation and the keyed testing-laptop G/Ask dry run. Aziz
does not add/use a key; Rayan reports whether both responses say `source:"gemini"`.

Run the opt-in soak from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/soak.py --output docs/validation/soak-2026-11-07.json
```

The runner uses the actual paced Hub loop with three robots, seed 7, the trained
detector and fixed demo zones. It advances **1,200 simulated seconds** with speed
set to **10x**, processes tick/maps/event envelopes, and measures process working
set/peak RSS in decimal MB. API keys are never used. Feature toggles are explicitly
off for this Version 1/default-path soak; optional features need separate dry runs.
It does not replace Rayan's proposed `server/tests/test_soak.py` or claim an actual
two-phone/screen LAN soak.

The JSON report records simulated duration, actual wall duration/speed, current and
peak RSS, growth after warmup, detector, deliveries and samples. Memory cap is
500 MB, growth cap 25 MB after warmup; target pace passes at >=9.5x. The command exits
nonzero if any criterion fails. A configured 10x speed does **not** prove achieved
10x throughput: check `ok`, `actual_speed` and `error` in the report. This test covers
20 minutes of simulated time, not a 20-minute wall-clock test.

## Measured integration results

- Rayan's opt-in scripted stress test (imported unchanged from commit `9310067`):
  **passed**, 1,200 sim seconds in 73 seconds wall, 16.5x unpaced throughput,
  4,622 events, RSS settled around 326 MiB and stayed flat. This includes rubble,
  overcurrent, overload, relay toggles and mode switches. Run separately with
  `DZ_SOAK=1 python -m pytest -q tests/test_soak.py -s` from `server/`.
- Paced Hub/default demo-plan run: no exceptions, all three survivors reported,
  1,201 sim seconds in 156.92 seconds wall, 353.58 decimal MB peak RSS, 9.62 MB
  growth after warmup. **Pace criterion failed:** 7.654x achieved with speed set
  to 10x. This is not a clean 10x throughput pass.
- Profile of the first 250 sim seconds: robot step 41.47/47.58 cumulative seconds,
  frontier clustering 23.12 seconds, A* 7.04 seconds, DTN step 1.43 seconds.
  These are overlapping profiled times, not independent unprofiled benchmarks.
  Rayan's review independently reports the same exploration bottleneck.

Raw paced samples and summaries are in `docs/validation/`. The cached memory
sampler/failure-reporting runner received a short smoke run after the full paced
measurement. Rayan owns planner performance work; robot policy was not edited.
