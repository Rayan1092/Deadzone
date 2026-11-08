# One HTTPS address for the demo

From this Windows demo checkout, with Python dependencies and `web/node_modules`
installed:

```powershell
.\.venv\Scripts\python.exe -u scripts/demo_tunnel.py
```

The launcher installs a portable official Cloudflare binary under ignored
`.demo/bin/` if needed, checks its SHA256 against official release metadata,
builds the frontend, binds FastAPI to loopback port 8000, and starts a Quick
Tunnel. Use `--port 8020` if another server occupies 8000; it refuses to expose an
already-occupied port. `--skip-build` reuses an existing build; `--install-only`
only installs/checks cloudflared. No service, Vercel or Supabase setup is needed.

Read the generated URL from the launcher or `.demo/tunnel.json`. That one HTTPS
origin serves `/`, `/phone`, `/api/*`, `/crops/*` and `/ws/*` (WSS). The launcher
sets `DZ_PUBLIC_URL` before starting FastAPI so QR uses this same origin. The
frontend already derives WSS from the page protocol. Do not put a separate Vite
URL or plain HTTP laptop address in the phone page.
Use `http://127.0.0.1:<port>` for the laptop's presenter screen; its override
credential then stays on loopback. QR still points phones at the HTTPS origin.

The backend starts paused: seed 7, three robots, 2x, control leases enabled, voice
and Gemini disabled. Explicit `--voice` and `--gemini` opt in independently for
keyed testing-laptop dry runs. Other gates keep their explicit process settings.
The launcher does not create/read an API key. Its generated presenter credential
is in `.demo/presenter-token.txt` while running, for the presenter only. Logs and
the credential never go into git. Ctrl+C stops the two processes started by this
launcher and removes live state/credential files. It does not stop an unrelated
existing server. Keep this launcher terminal alive during the demo.
Preload P-1 quietly using `docs/DEMO.md` and `/api/plan?check=false` before rehearsal.

Check the public address before handing out the QR:

```powershell
$demo = Get-Content .demo/tunnel.json | ConvertFrom-Json
.\.venv\Scripts\python.exe scripts/check_tunnel.py --url $demo.url --leases
```

This checks HTTPS HTML/assets/API/QR and screen plus two phone WSS connections.
`--leases` briefly claims a **free** R1, verifies second-controller rejection,
heartbeat, public broadcasts and non-holder manual/voice rejection, then releases
it. It never overrides someone else's lease or dispatches a robot command. Omit
`--leases` during a live session to keep the probe read-only. Optional `--output`
writes the result. This does not establish venue Wi-Fi or phone microphone access.

## Early venue Wi-Fi dry run

1. Run the launcher on the actual demo laptop connected to venue Wi-Fi. Open the
   HTTPS page on each physical phone over that Wi-Fi, not localhost on the phone.
2. Open `<generated origin>/mic-check`. Tap Record, grant permission, speak for
   five seconds, then play it back. Audio stays on the phone; no upload or key.
   Check both intended phone browsers. If denied, restore microphone permission
   in that browser/site's settings and retry. Desktop HTTP/WSS success alone does
   not prove recording works.
3. Run the probe above, then Yusuf's Take/Release UI when it lands: two phones
   compete for the same robot, second stays disabled; release/disconnect/heartbeat
   expiry frees it; presenter override frees it without disconnecting the phone.
4. Keep one page connected for several minutes, background/reopen a phone, and
   verify reconnect uses WSS and requires reclaim. Record actual devices/network,
   permission results and observed failures in the team history.
5. If venue firewall blocks tunnel connectivity, switch laptop/phones to the
   hotspot and repeat. Launcher requests HTTP/2 transport rather than QUIC.
   Big-screen microphone on localhost and manual phone control remain fallbacks.

Cloudflare Quick Tunnels use a temporary address that changes on restart and have
no uptime guarantee. Test early and regenerate the QR after restarting. Anyone
with the address can view the demo; presenter credentials stay separate. See
[Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
and [official downloads](https://developers.cloudflare.com/tunnel/downloads/).

The full backend speech/intent/safety/DTN acknowledgement/TTS contract is in
[VOICE.md](VOICE.md). Provider calls have been verified with mocked transports;
the real keyed pipeline and Yusuf's push-to-talk UI still need dry runs. User
confirmed the phone microphone preflight works on venue Wi-Fi; that alone does
not establish STT, Gemini intent or synthesized speech acceptance.
