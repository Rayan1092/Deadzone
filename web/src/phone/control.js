// Direct control of a robot from a phone, on Aziz's lease API: one controller per robot,
// claimed for 15 s and kept alive by a heartbeat every 5 s; anyone else sees it locked. The
// server issues this phone's controller token in its hello (planner role, leases on). Every
// state shown here comes from the server: the lease table it broadcasts, the answer to a
// command, and the robot's acknowledgement once it is delivered to the command post.

export const HEARTBEAT_MS = 5000
export const DARK_S = 3   // a report older than this: the robot is out of radio contact

export function leaseOf(leases, robot) {
  return leases?.robots?.find((r) => r.robot === robot) ?? null
}

// 'off' (leases disabled on this server) | 'free' | 'me' | 'other'
export function holder(leases, robot, client) {
  if (!leases?.enabled) return 'off'
  const c = leaseOf(leases, robot)?.controller
  if (!c) return 'free'
  return c.client === client ? 'me' : 'other'
}

async function call(path, body, token, fetcher = fetch) {
  const res = await fetcher(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { 'X-Controller-Token': token } : {}) },
    body: JSON.stringify(body),
  })
  let data = null
  try { data = await res.json() } catch { /* empty or not JSON */ }
  if (!res.ok) {
    const detail = data?.detail
    const error = new Error(typeof detail === 'string' ? detail : detail?.msg ?? `Request failed (${res.status})`)
    error.code = detail?.code ?? 'request'
    throw error
  }
  return data
}

export const claim = (robot, name, token, fetcher) => call('/api/leases/claim', { robot, name }, token, fetcher)
export const release = (robot, token, fetcher) => call('/api/leases/release', { robot }, token, fetcher)
export const heartbeat = (robot, token, fetcher) => call('/api/leases/heartbeat', { robot }, token, fetcher)

let seq = 0
// intent: { action: 'hold' | 'resume' | 'return_home' | 'explore_zone', zone? }
export function command(robot, intent, token, fetcher) {
  const request_id = `p${Date.now().toString(36)}${(seq++).toString(36)}`
  return call('/api/robot-command', { robot, ...intent, request_id }, token, fetcher)
}

// The robot's own answer, only once its bundle reached the command post.
export const ackFor = (view, cmdId) => (cmdId && view?.command_acks?.find((a) => a.cmd_id === cmdId)) || null

// What the camera panel can honestly show: a delivered camera frame when the server sends one
// (Rayan's contract B: telemetry `camera` { t, hits } under DZ_CAMERA_TELEMETRY=1, kept by
// Aziz as cmd_view robots[].camera), else the newest delivered thermal crop from this robot.
// Never a frame that was not delivered.
export function lastFrame(report, survivors, robot) {
  if (report?.camera) return { kind: 'frame', t: report.camera.t, frame: report.camera }
  const crop = (survivors ?? []).filter((s) => s.by === robot && s.crop)
    .sort((a, b) => (b.t ?? b.reported_t) - (a.t ?? a.reported_t))[0]
  return crop ? { kind: 'crop', t: crop.t ?? crop.reported_t, crop } : null
}

export const isDark = (report) => !report || report.stale_s > DARK_S
