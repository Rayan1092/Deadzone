// The robots' rate monotonic task set in plain words (server/deadzone/robot/scheduler.py TASKS:
// name, period ms, WCET ms; shorter period = higher priority). No imports, so Node can test it.
export const TASK_INFO = {
  safety: { label: 'Lidar scan', period: 50, wcet: 2, why: 'reads the lidar and stops the robot before it touches anything; highest priority, never misses' },
  motion: { label: 'Plan', period: 100, wcet: 8, why: 'follows the planned path and steers the wheels' },
  comms: { label: 'Radio', period: 200, wcet: 10, why: 'sends and forwards data bundles toward the command post, stores them while the link is down' },
  mapping: { label: 'Map update', period: 200, wcet: 25, why: 'adds the latest lidar scan to the robot\'s map and picks the next frontier' },
  perception: { label: 'Thermal', period: 500, wcet: 40, why: 'runs the onboard person classifier on warm spots from the thermal camera; first to miss when the CPU is overloaded' },
  battery: { label: 'Battery', period: 1000, wcet: 2, why: 'checks the charge left against the energy needed to drive home' },
}
export const TASK_ORDER = ['safety', 'motion', 'comms', 'mapping', 'perception', 'battery']

// Liu & Layland: rate monotonic meets every deadline while utilization <= n (2^(1/n) - 1)
export const RM_BOUND = TASK_ORDER.length * (2 ** (1 / TASK_ORDER.length) - 1) // 0.7348 for 6 tasks
export const declaredUtilization = () => TASK_ORDER.reduce((u, n) => u + TASK_INFO[n].wcet / TASK_INFO[n].period, 0)

// Fraction of the 100 ms frame the CPU was busy (telemetry `tasks`: {name, start, dur, missed})
export function frameLoad(tasks) {
  return Math.min(1, (tasks ?? []).reduce((sum, t) => sum + (t.dur ?? 0), 0) / 100)
}

// Positions (0-100 ms within the frame that just ended at sim `time` s) where a job of a task
// with this period is released, which is also where the previous job is due.
export function deadlineTicks(time, period) {
  const start = Math.round((time - 0.1) * 1000)
  const out = []
  for (let p = 0; p <= 100; p++) if ((start + p) % period === 0) out.push(p)
  return out
}
