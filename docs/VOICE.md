# Voice pipeline contract (posted before implementation)

Enable `DZ_VOICE=1` only for a dry run. It implies the exclusive lease checks in
[CONTROL-LEASES.md](CONTROL-LEASES.md). User confirmed the existing phone
`/mic-check` works on venue Wi-Fi. Actual STT/intent/TTS acceptance is separate.

## Requests for Yusuf

Every command request sends `X-Controller-Token` from the private controller hello.
Keep the phone heartbeat running every five wall seconds while recording/waiting.
The selected robot comes from the request, never the model. The backend checks the
same live lease grant again after asynchronous work and immediately before enqueue;
expiry, release/reclaim or reset during processing rejects the stale operation.

- POST `/api/voice`: JSON `{robot:"R2",text:"explore the warehouse",request_id:"optional-client-uuid"}`.
  `text` is a real browser transcript (the labelled STT fallback), trimmed 1-1000
  chars. Gemini parses one whitelisted intent; no deterministic guessed command
  when Gemini is unavailable. Missing key/timeout/provider failure returns 503.
- POST `/api/voice/audio?robot=R2&request_id=optional-client-uuid`: raw recording
  bytes, Content-Type `audio/webm`, `audio/mp4`, `audio/wav`, `audio/ogg` or
  `audio/mpeg` (codec parameters allowed). Limit 2 MiB. ElevenLabs STT then Gemini
  intent, with a 10-second deadline for each provider step. Missing STT key/failure
  returns 503 `stt_unavailable`; UI offers labelled browser speech recognition.
  No files, audio URLs or supplied filenames are accepted/stored.
- POST `/api/robot-command`: typed manual `{robot,action,zone?,target?,request_id?}`.
  Actions: `explore_zone`, `go_to`, `return_home`, `hold`, `resume`. Zone is a public
  prior room ID/name; target is explicit `[x,y]` metres. Both use the same safety
  and enqueue path as voice. Existing resume works with leases; other actions also
  require `DZ_VOICE=1` until dry run. No arbitrary model polygon or robot selection.

Queued response (HTTP 200):

```json
{"queued":true,"cmd_id":"V-...","robot":"R2","action":"explore_zone",
 "command":{"cmd":"explore_zone","zone":{"id":"E1","name":"Warehouse Floor","poly":[[1,1],[2,1],[2,2],[1,2]]}},
 "transcript":"explore the warehouse","stt_source":"browser","intent_source":"gemini",
 "safety":{"ok":true,"violations":[]},"status":"waiting_for_robot","issued_t":125.0}
```

Manual requests label sources `manual`. A safety refusal returns HTTP 200 with
`queued:false,status:"refused"`, the same parsed command/source fields, safety
violations and `say` explaining refusal. It is a **Command safety refusal**, not a
robot acknowledgement. Travel uses the existing SafetyChecker over public prior,
delivered map/battery/relays and current plan no-go restrictions. Lost-link policy
comes from the robot's delivered dispatched-plan assignment. Hold/resume add no
travel, and the robot still decides fault/safe-stop/route feasibility on receipt.

`request_id` makes retries idempotent per live controller connection for five
minutes (bounded 256 entries); reuse with different input is 409, in-progress retry
409, capacity/concurrent command processing 429. Omit it only for a new operation.
Reset invalidates pending work and the cache. No enqueue or robot mutation happens
on provider error, unsupported/ambiguous intent, stale lease or failed safety.

## Delivered acknowledgement, then speech

Rayan's priority-1 `command` / `command_ack` payload is unchanged. Backend assigns
unique cmd_id and enqueues at CMD; dark robots answer late over normal custody.
`command_ack` gets explicit priority 1 in PRIO. CommandPost validates source/shape,
keeps the latest ack per cmd_id (max 256), ignores duplicates/older states and emits
`command_ack_reported {...ack,reported_t,delay_s:now-t}` **on delivery only**.
Phones and screens receive that event; delivered `command_acks` in Command views
allow reconnect recovery. Never play speech on Reality's command_received or on
the queued HTTP response. Completed wins over accepted at the same timestamp.

POST `/api/voice/tts` with `{cmd_id}` reads only an actually delivered ack from the
current Command epoch; no arbitrary text or voice ID accepted. Returns
`{source:"elevenlabs",robot,cmd_id,status,t,text,audio:{mime_type:"audio/mpeg",data_base64:"..."}}`,
or `{source:"browser",robot,cmd_id,status,t,text}` for labelled browser speech when
the key/voice is missing, provider times out or synthesis fails. Unknown/undelivered
ack is 404, reset during synthesis 409. This is read-only and needs no robot lease.
Server cache holds at most 32 delivered ack versions per reset epoch; subtitles
always use returned text/status.

Config: ignored `server/.env` / process-only `ELEVENLABS_API_KEY`,
`ELEVENLABS_VOICE_R1`, `_R2`, `_R3` (distinct server-selected voice IDs). Default
STT model `scribe_v2`, TTS `eleven_flash_v2_5`; optional `ELEVENLABS_STT_MODEL` /
`ELEVENLABS_TTS_MODEL`. Intent uses existing current Flash default / `GEMINI_MODEL`
and `GEMINI_API_KEY`; separate from the read-only G/Ask tools, which never enqueue
commands. No key will be added/used here; provider checks use mocked transports.

Provider interfaces checked against official [ElevenLabs STT](https://elevenlabs.io/docs/api-reference/speech-to-text/convert),
[TTS](https://elevenlabs.io/docs/api-reference/text-to-speech/convert), and
[Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output).
Yusuf owns push-to-talk, transcript/parsed command card, pending/locked state,
labelled fallbacks and playback. Full keyed pipeline/two-phone UI dry run remains
required before enabling on stage.

Tunnel launcher opt-in (contract before code): `--voice` sets DZ_VOICE=1 for a
keyed dry run; `--gemini` independently enables G/Ask. Defaults keep both off.
Only Rayan/testing laptop supplies the ignored keys and reports real provider
sources; no agent key insertion or keyed provider call is part of this validation.
