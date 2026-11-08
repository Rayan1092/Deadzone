// Robot card helpers for the big-screen sidebar (pure, so they can be checked without a DOM).
//
// Link quality in words, from the robot's best radio link (tick.reality.robots[].link):
//   Strong  linked and above -75 dBm: the upper half of the radio model's useful range
//           (server/deadzone/network/propagation.py: full rate at -60 dBm, link drops below -88)
//   Weak    linked at -75 dBm or below: slower links, close to dropping out
//   Lost    no route to the command post
export const STRONG_DBM = -75

export function linkQuality(link) {
  if (!link?.up) return { word: 'Lost', cls: 'lost', dbm: null }
  const dbm = Math.round(link.rssi)
  return dbm > STRONG_DBM ? { word: 'Strong', cls: 'strong', dbm } : { word: 'Weak', cls: 'weak', dbm }
}

// "−71 dBm · Strong" (a real minus sign) or "Lost".
export function linkText(link) {
  const q = linkQuality(link)
  return q.dbm == null ? q.word : `${String(q.dbm).replace('-', '−')} dBm · ${q.word}`
}

// How long Command has not heard from a robot, from Command's own record (what reached the
// antenna), only while the robot is out of contact. null while linked or before any report.
export function lastContact(link, cmd, time) {
  if (link?.up || !cmd || cmd.last_seen == null) return null
  const s = Math.max(0, Math.floor(time - cmd.last_seen))
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`
}
