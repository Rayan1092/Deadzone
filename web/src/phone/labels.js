// Display names are separate from the stable identifiers used by the API.
export const robotName = (id, robots = []) => robots.find((r) => r.id === id)?.name ?? 'Robot'
export const robotCount = (count) => `${count} ${count === 1 ? 'robot' : 'robots'}`
export function regionName(id, draft) {
  const zone = draft?.zones?.findIndex((r) => r.id === id) ?? -1
  if (zone >= 0) return `Search area ${zone + 1}`
  const noGo = draft?.no_go?.findIndex((r) => r.id === id) ?? -1
  return noGo >= 0 ? `No-go area ${noGo + 1}` : 'Search area'
}
export function publicText(value, hello, draft) {
  let text = String(value ?? '')
  if (/DZ_|\/api\/|plan_id|request_id|controller_token|TypeError|Failed to fetch|NetworkError/i.test(text)) {
    return 'That action could not be completed. Check your connection and try again.'
  }
  const names = Object.fromEntries((hello?.robots ?? []).map((r) => [r.id, r.name]))
  for (const r of [...(draft?.zones ?? []), ...(draft?.no_go ?? [])]) names[r.id] = regionName(r.id, draft)
  text = text.replace(/\b[A-Za-z0-9_]+(?:[.-][A-Za-z0-9_]+)*\b/g, (word) => names[word] ?? word)
  text = text.replace(/\bP-\d+\b/g, 'the plan').replace(/\b(?:R\d+|RL\d+|CMD)\b/g, 'the robot')
    .replace(/\b(?:phone|judge)-[\w.-]+\b/g, 'another field unit').replace(/\bPresenter\b/gi, 'Console')
  return text ? text[0].toUpperCase() + text.slice(1) : 'Please try again.'
}
export const connectionLabel = (status) => ({
  connecting: 'Connecting', live: 'Connected', reconnecting: 'Reconnecting', unreachable: 'Server unreachable',
}[status] ?? 'Connecting')

export async function probeServer(signal, fetcher = fetch) {
  try {
    const response = await fetcher('/api/health', { signal, cache: 'no-store' })
    return response.ok && (await response.json()).ok === true
  } catch { return false }
}
