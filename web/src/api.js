const BASE = import.meta.env.VITE_API_BASE || ''

async function request(path, options) {
  const res = await fetch(BASE + path, options)
  let data = null
  try {
    data = await res.json()
  } catch {
    /* 非 JSON 响应 */
  }
  return { status: res.status, data }
}

export async function fetchLimits() {
  const { data } = await request('/api/limits')
  return data
}

export async function solve(payload) {
  const { status, data } = await request('/api/solve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return { status, data }
}
