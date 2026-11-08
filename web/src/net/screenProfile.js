// HTTPS viewers use less observer traffic; localhost retains the complete view.
export function screenPath(location, deltas = true) {
  const page = new URLSearchParams(location.search)
  const host = location.hostname
  const local = host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local') ||
    host === '::1' || host === '[::1]' || /^127\./.test(host) || /^10\./.test(host) ||
    /^192\.168\./.test(host) || /^172\.(1[6-9]|2\d|3[01])\./.test(host)
  const lite = page.has('lite') ? !['0', 'false'].includes(page.get('lite').toLowerCase()) :
    location.protocol === 'https:' && !local
  const params = new URLSearchParams()
  if (deltas) params.set('map_deltas', '1')
  if (lite) params.set('lite', '1')
  return '/ws/screen' + (params.size ? '?' + params : '')
}
