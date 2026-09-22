// Deterministic parsers for the textarea based editors. Input content is
// always preserved by the UI; these functions only produce structured data or
// precise field errors.

const isAscii = (s) => s.length > 0 && [...s].every((c) => c.charCodeAt(0) < 128)

export function parseStates(text) {
  const tokens = text
    .split(/[\n,;，；\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
  return tokens
}

export function parseObservations(text) {
  return text
    .split(/[\n,;，；\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

// Each line: id, source, target, code (comma / tab / | / >=2 spaces separated)
export function parseTransitions(text) {
  const rows = []
  const errors = []
  text.split(/\r?\n/).forEach((raw, i) => {
    const line = raw.trim()
    if (!line || line.startsWith('#')) return
    const parts = line.split(/\s*[,\t|]\s*|\s{2,}/).map((s) => s.trim()).filter((s) => s !== '')
    if (parts.length !== 4) {
      errors.push({ line: i + 1, raw, message: `需要 4 列（id, source, target, code），实际 ${parts.length} 列` })
      return
    }
    rows.push({ id: parts[0], source: parts[1], target: parts[2], code: parts[3], line: i + 1 })
  })
  return { rows, errors }
}

export function validateClient({ states, transitions, start, end, observations }) {
  const problems = { states: [], transitions: [], endpoints: [], observations: [] }

  if (states.length < 2) problems.states.push(`至少需要 2 个状态，当前 ${states.length} 个`)
  if (states.length > 80) problems.states.push(`最多 80 个状态，当前 ${states.length} 个`)
  for (const s of states) {
    if (!isAscii(s)) problems.states.push(`状态名必须为非空 ASCII：${s}`)
  }
  const dupStates = states.filter((s, i) => states.indexOf(s) !== i)
  if (dupStates.length) problems.states.push(`状态名重复：${[...new Set(dupStates)].join(', ')}`)

  if (transitions.length < 1) problems.transitions.push('至少需要 1 条迁移')
  if (transitions.length > 300) problems.transitions.push(`最多 300 条迁移，当前 ${transitions.length} 条`)
  const ids = new Set()
  const stateSet = new Set(states)
  for (const t of transitions) {
    if (!isAscii(t.id)) problems.transitions.push(`第 ${t.line} 行：迁移 id 非法（${t.id}）`)
    if (ids.has(t.id)) problems.transitions.push(`第 ${t.line} 行：迁移 id 重复（${t.id}）`)
    ids.add(t.id)
    if (!isAscii(t.code)) problems.transitions.push(`第 ${t.line} 行：事件码非法（${t.code}）`)
    if (!stateSet.has(t.source)) problems.transitions.push(`第 ${t.line} 行：源状态 ${t.source} 未声明`)
    if (!stateSet.has(t.target)) problems.transitions.push(`第 ${t.line} 行：目标状态 ${t.target} 未声明`)
  }

  if (!stateSet.has(start)) problems.endpoints.push(`初态 ${start || '(空)'} 不在状态列表中`)
  if (!stateSet.has(end)) problems.endpoints.push(`末态 ${end || '(空)'} 不在状态列表中`)

  if (observations.length < 1) problems.observations.push('至少需要 1 个观测事件')
  if (observations.length > 200) problems.observations.push(`最多 200 个观测事件，当前 ${observations.length} 个`)
  for (const o of observations) {
    if (!isAscii(o)) problems.observations.push(`事件码必须为 ASCII：${o}`)
  }

  const ok = Object.values(problems).every((list) => list.length === 0)
  return { ok, problems }
}

export const SAMPLE = {
  states: ['ATM', 'ROUGH', 'FINE', 'HIGH', 'COAT', 'VENT_BACK'],
  transitionText: [
    '# id, source, target, event_code',
    'rv1, ATM, ROUGH, RV_OPEN',
    'gv1, ROUGH, FINE, GV_OPEN',
    'tmp, FINE, HIGH, TMP_OK',
    'ev1, HIGH, COAT, EV_FIRE',
    'ev2, COAT, COAT, EV_FIRE',
    'ev0, COAT, HIGH, EV_STOP',
    'gv0, HIGH, FINE, GV_CLOSE',
    'rv0, FINE, ROUGH, GV_CLOSE',
    'vent, ROUGH, ATM, VENT_OPEN',
  ].join('\n'),
  start: 'ATM',
  end: 'ATM',
  observationText: ['RV_OPEN', 'GV_OPEN', 'TMP_OK', 'EV_FIRE', 'EV_STOP', 'VENT_OPEN'].join(', '),
}
