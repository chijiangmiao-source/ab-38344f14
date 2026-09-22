// Thin client for the interlock completion API. All requests use same-origin
// relative URLs; nginx (prod) and vite (dev) proxy /api and /health(api) .

export async function fetchHealth() {
  // Same-origin: nginx proxies /health to the api container; the vite dev
  // server does the same via its proxy config.
  const r = await fetch('/health', { headers: { Accept: 'application/json' } })
  if (!r.ok) throw new Error(`health ${r.status}`)
  return r.json()
}

export async function solve(payload) {
  const r = await fetch('/api/solve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  let body = null
  try {
    body = await r.json()
  } catch {
    /* non-JSON error page */
  }
  if (r.ok) return { ok: true, data: body }
  if (body && body.error) {
    return {
      ok: false,
      status: r.status,
      code: body.error.code,
      message: body.error.message,
      observationIndex: body.error.observation_index ?? null,
      eventCode: body.error.event_code ?? null,
    }
  }
  return { ok: false, status: r.status, code: 'network', message: `请求失败 (HTTP ${r.status})` }
}
