# Observer stream optimization

`DZ_STREAM_OPTIMIZE=1` at server/Hub startup enables a 15 Hz wall-clock cap on
periodic screen ticks, at most 24 lidar points per screen robot, and suppression
of unchanged periodic maps. The gate defaults off. Sensors, mapping, autonomy,
events, controls and phone update cadence are unchanged. Connect, reset and
explicit forced state refreshes bypass the periodic cap.

Ordinary clients keep base64 grids. With the gate on, clients with a decoder can
request `/ws/screen?compact=1` or `/ws/phone?compact=1`. Without the gate, a compact
request closes with code 1008. `hello.data.stream` declares `map_encoding`,
`compact_available`, `screen_hz` and `lidar_max_points`. Compact screen `maps`
adds `encoding: "zlib-base64"`; compact phone `cmd_view` adds
`map_encoding: "zlib-base64"`. Other messages remain ordinary JSON.

Decode each compressed grid as base64, then zlib, to recover the identical
row-major uint8 bytes:

```python
raw_grid = zlib.decompress(base64.b64decode(value))
```

Grid keys are `reality`, `command`, and optional future `belief` /
`belief_command`. Compression preserves optional metadata; it never fabricates
missing belief grids. Phones receive only their existing Command `map`. Yusuf
must add the opt-in decoder before a browser requests compact mode; ordinary
clients can already use the compatible tick cap, lidar thinning and map dedup.

Optimized maps include overall `version` and per-grid `versions`. Only a changed
grid increments its own version. Initial reads do not consume pending broadcasts
for existing clients. Clear version caches on `hello`; counters restart for each
incident. Forced refreshes still send full state even when bytes are unchanged.

Run `.venv/Scripts/python scripts/measure_stream.py` from the repo root to compare
legacy, optimized base64 and optimized compact output through the actual Hub
broadcaster on one shared seed-7 replay. It uses 3 robots, the demo plan and
R/F/O inputs, a deterministic 30 Hz input clock (3x simulation speed), and one
initial forced frame. It counts screen UTF-8 JSON application bytes, excluding
WebSocket/TLS overhead, hello and plan_state. Every compact map is checked for a
lossless round trip. This measures payload and cadence, not browser FPS.

Measured results are recorded in `stream-measurements.json` alongside this file.
Network traffic has its separate gate and contract in [TRAFFIC.md](TRAFFIC.md).
