import { useMemo, useState } from 'react'

// Pure-SVG directed multigraph view. States are placed on a circle; parallel
// edges fan out as quadratic curves, self loops are small arcs. The canonical
// completion path is overlaid: consumed edges solid blue with the observation
// ordinal, inserted edges dashed red. A boundary selector shows every state
// that can occur at that boundary in SOME optimal completion (green halo).

const COLORS = {
  edge: '#9aa7b4',
  consumed: '#1d6fe0',
  inserted: '#e0552b',
  mixed: '#8a4fd0',
  possible: '#2fae66',
  start: '#d9f7e7',
  end: '#fde9d9',
  nodeFill: '#ffffff',
  nodeStroke: '#46586c',
}

function layout(states, width, height) {
  const cx = width / 2
  const cy = height / 2
  const r = Math.min(width, height) / 2 - 70
  const pos = {}
  const n = states.length
  states.forEach((s, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / n
    pos[s] = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }
  })
  return pos
}

function edgeGeometry(p1, p2, fan, fanTotal, selfLoop) {
  if (selfLoop) {
    return {
      d: `M ${p1.x} ${p1.y} q 26 -34 0 -2`,
      mid: { x: p1.x + 30, y: p1.y - 30 },
      angle: -Math.PI / 2,
    }
  }
  const dx = p2.x - p1.x
  const dy = p2.y - p1.y
  const len = Math.hypot(dx, dy) || 1
  const ux = dx / len
  const uy = dy / len
  const px = -uy
  const py = ux
  // symmetric fan offset
  const spread = fanTotal > 1 ? (fan - (fanTotal - 1) / 2) * 26 : 0
  const mx = (p1.x + p2.x) / 2 + px * spread
  const my = (p1.y + p2.y) / 2 + py * spread
  const mid = { x: mx, y: my }
  return {
    d: `M ${p1.x} ${p1.y} Q ${mx} ${my} ${p2.x} ${p2.y}`,
    mid,
    angle: Math.atan2(p2.y - my, p2.x - mx),
  }
}

export default function GraphView({ states, transitions, start, end, result, failedBoundary }) {
  const size = 640
  const positions = useMemo(() => layout(states, size, size), [states])

  const fanTotals = useMemo(() => {
    const m = new Map()
    for (const t of transitions) {
      const key = `${t.source}=>${t.target}`
      m.set(key, (m.get(key) ?? 0) + 1)
    }
    return m
  }, [transitions])

  const fanIndexMap = useMemo(() => {
    const seen = new Map()
    const out = new Map()
    transitions.forEach((t, i) => {
      const key = `${t.source}=>${t.target}`
      const idx = seen.get(key) ?? 0
      seen.set(key, idx + 1)
      out.set(i, idx)
    })
    return out
  }, [transitions])

  // path occurrences per edge id (edges may repeat around cycles)
  const pathOccurrences = useMemo(() => {
    const map = new Map()
    if (!result) return map
    result.canonical_sequence.forEach((step) => {
      const list = map.get(step.edge_id) ?? []
      list.push(step)
      map.set(step.edge_id, list)
    })
    return map
  }, [result])

  const boundaries = result ? result.boundary_states : []
  const [boundary, setBoundary] = useState(0)
  const effectiveBoundary = Math.min(boundary, boundaries.length - 1)
  const possible = useMemo(() => {
    if (!boundaries.length) return new Set()
    return new Set(boundaries[Math.max(0, effectiveBoundary)].states)
  }, [boundaries, effectiveBoundary])

  const nodeR = 22

  return (
    <div className="graph-panel">
      {result && (
        <div className="boundary-control">
          <label>
            观测边界：
            <input
              type="range"
              min={0}
              max={boundaries.length - 1}
              value={effectiveBoundary}
              onChange={(e) => setBoundary(Number(e.target.value))}
            />
            <strong>{effectiveBoundary}</strong> / {boundaries.length - 1}
          </label>
          <span className="possible-list">
            最优补全在此边界的可能状态：
            {possible.size
              ? [...possible].map((s) => <em key={s} className="pill possible">{s}</em>)
              : <em className="pill">（无）</em>}
          </span>
        </div>
      )}
      <svg viewBox={`0 0 ${size} ${size}`} className="graph-svg" role="img"
           aria-label="状态迁移图与规范补全路径">
        <defs>
          <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3"
                  orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L8,3 L0,6 Z" fill={COLORS.edge} />
          </marker>
          <marker id="arrow-consumed" markerWidth="10" markerHeight="10" refX="8" refY="3"
                  orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L8,3 L0,6 Z" fill={COLORS.consumed} />
          </marker>
          <marker id="arrow-inserted" markerWidth="10" markerHeight="10" refX="8" refY="3"
                  orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L8,3 L0,6 Z" fill={COLORS.inserted} />
          </marker>
          <marker id="arrow-mixed" markerWidth="10" markerHeight="10" refX="8" refY="3"
                  orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L8,3 L0,6 Z" fill={COLORS.mixed} />
          </marker>
        </defs>

        {transitions.map((t, i) => {
          const fan = fanIndexMap.get(i) ?? 0
          const total = fanTotals.get(`${t.source}=>${t.target}`) ?? 1
          const selfLoop = t.source === t.target
          const p1 = positions[t.source]
          const p2 = positions[t.target]
          // shorten to node border
          if (!p1 || !p2) return null
          let from = p1
          let to = p2
          if (!selfLoop) {
            const dx = p2.x - p1.x
            const dy = p2.y - p1.y
            const len = Math.hypot(dx, dy) || 1
            const ux = dx / len
            const uy = dy / len
            from = { x: p1.x + ux * nodeR, y: p1.y + uy * nodeR }
            to = { x: p2.x - ux * nodeR, y: p2.y - uy * nodeR }
          }
          const g = edgeGeometry(from, to, fan, total, selfLoop)
          const occ = pathOccurrences.get(t.id)
          const onPath = !!occ
          // The same edge id can occur several times around a cycle and play
          // different roles at different occurrences; show that faithfully.
          const roles = onPath ? new Set(occ.map((s) => s.role)) : new Set()
          const role =
            !onPath ? 'idle' : roles.size > 1 ? 'mixed' : [...roles][0]
          const stroke =
            role === 'consumed' ? COLORS.consumed
            : role === 'inserted' ? COLORS.inserted
            : role === 'mixed' ? COLORS.mixed
            : COLORS.edge
          const marker =
            role === 'consumed' ? 'url(#arrow-consumed)'
            : role === 'inserted' ? 'url(#arrow-inserted)'
            : role === 'mixed' ? 'url(#arrow-mixed)'
            : 'url(#arrow)'
          const consumedOrd = occ
            ? occ.filter((s) => s.role === 'consumed').map((s) => s.observation_index)
            : []
          const insertedTimes = occ ? occ.filter((s) => s.role === 'inserted').length : 0
          return (
            <g key={t.id} className={onPath ? 'edge on-path' : 'edge'}>
              <path
                d={g.d}
                fill="none"
                stroke={stroke}
                strokeWidth={onPath ? 3.2 : 1.3}
                strokeDasharray={role === 'inserted' ? '7 5' : role === 'mixed' ? '10 4 2 4' : undefined}
                markerEnd={marker}
              />
              <text
                x={g.mid.x}
                y={g.mid.y - 4}
                textAnchor="middle"
                className={onPath ? 'edge-label hot' : 'edge-label'}
                fill={onPath ? stroke : '#6b7886'}
              >
                {t.id}{onPath ? ` · ${t.code}` : ''}
              </text>
              {onPath && (consumedOrd.length > 0 || insertedTimes > 0) && (
                <text x={g.mid.x} y={g.mid.y + 11} textAnchor="middle"
                      className="obs-badge" fill={stroke}>
                  {consumedOrd.length ? `#${consumedOrd.join(',#')}` : ''}
                  {consumedOrd.length && insertedTimes ? ' + ' : ''}
                  {insertedTimes ? `插入×${insertedTimes}` : ''}
                </text>
              )}
            </g>
          )
        })}

        {states.map((s) => {
          const p = positions[s]
          const isStart = s === start
          const isEnd = s === end
          const isPossible = possible.has(s)
          return (
            <g key={s} transform={`translate(${p.x},${p.y})`}>
              {isPossible && <circle r={nodeR + 8} fill="none" stroke={COLORS.possible}
                                     strokeWidth={3} strokeDasharray="4 3" />}
              <circle
                r={nodeR}
                fill={isStart ? COLORS.start : isEnd ? COLORS.end : COLORS.nodeFill}
                stroke={COLORS.nodeStroke}
                strokeWidth={1.6}
              />
              <text textAnchor="middle" dy="0.35em" className="node-label">{s}</text>
              {(isStart || isEnd) && (
                <text textAnchor="middle" y={-nodeR - 8} className="endpoint-tag">
                  {isStart ? '初态' : ''}{isStart && isEnd ? '/' : ''}{isEnd ? '末态' : ''}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      {failedBoundary != null && (
        <div className="graph-hint">首个无法消费的观测位置：#{failedBoundary}</div>
      )}
    </div>
  )
}
