import { useMemo, useState } from 'react'
import { layoutCircle, edgeGeometry, NODE_RADIUS } from './layout'

const WIDTH = 860
const HEIGHT = 600

/** 边按迁移 id 汇总规范解中的使用方式。 */
function summarizeUsage(result) {
  const usage = new Map() // id -> { inserted: n, observed: [观测序号...] }
  if (!result) return usage
  result.canonical_sequence.forEach((id, i) => {
    const ev = result.canonical_events[i]
    const cur = usage.get(id) || { inserted: 0, observed: [] }
    if (ev == null) cur.inserted += 1
    else cur.observed.push(ev)
    usage.set(id, cur)
  })
  return usage
}

export default function GraphSvg({ states, transitions, result, selectedBoundary }) {
  const [hover, setHover] = useState(null)
  const pos = useMemo(() => layoutCircle(states, WIDTH, HEIGHT), [states])

  // 平行边（同端点不同标识）分配不同曲率
  const pairIndex = useMemo(() => {
    const counts = new Map()
    const map = new Map()
    for (const t of transitions) {
      const key = `${t.source}->${t.target}`
      const slot = counts.get(key) || 0
      counts.set(key, slot + 1)
      map.set(t.id, { slot, total: slot + 1, key })
    }
    // 最终 total
    for (const [, v] of map) {
      v.total = counts.get(v.key)
    }
    return map
  }, [transitions])

  const usage = useMemo(() => summarizeUsage(result), [result])

  const boundarySet = useMemo(() => {
    if (result && selectedBoundary != null) {
      return new Set(result.boundary_states[selectedBoundary] || [])
    }
    return new Set()
  }, [result, selectedBoundary])

  const tById = useMemo(() => new Map(transitions.map((t) => [t.id, t])), [transitions])

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="graph-svg"
      role="img"
      aria-label="状态迁移图"
    >
      <defs>
        <marker id="arrow-gray" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#9aa4b2" />
        </marker>
        <marker id="arrow-obs" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#1a7f37" />
        </marker>
        <marker id="arrow-ins" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#cf222e" />
        </marker>
      </defs>

      {transitions.map((t) => {
        const a = pos[t.source]
        const b = pos[t.target]
        if (!a || !b) return null
        const geo = edgeGeometry(pos, t.source, t.target, pairIndex.get(t.id))
        const u = usage.get(t.id)
        let cls = 'edge edge-idle'
        let marker = 'url(#arrow-gray)'
        let labelCls = 'edge-label edge-label-idle'
        if (u) {
          if (u.observed.length && u.inserted) {
            cls = 'edge edge-both'
            marker = 'url(#arrow-obs)'
            labelCls = 'edge-label edge-label-both'
          } else if (u.observed.length) {
            cls = 'edge edge-observed'
            marker = 'url(#arrow-obs)'
            labelCls = 'edge-label edge-label-observed'
          } else {
            cls = 'edge edge-inserted'
            marker = 'url(#arrow-ins)'
            labelCls = 'edge-label edge-label-inserted'
          }
        }
        const active = hover === t.id
        return (
          <g key={t.id}
            onMouseEnter={() => setHover(t.id)}
            onMouseLeave={() => setHover(null)}>
            <path d={geo.d} className={cls + (active ? ' edge-hover' : '')}
              markerEnd={marker} fill="none" />
            <text x={geo.labelX} y={geo.labelY} className={labelCls}
              textAnchor="middle" dominantBaseline="middle">
              {t.id}
              <tspan className="edge-code">:{t.event_code}</tspan>
            </text>
          </g>
        )
      })}

      {states.map((s) => {
        const p = pos[s]
        const inBoundary = boundarySet.has(s)
        return (
          <g key={s} className="node-group">
            {inBoundary && <circle cx={p.x} cy={p.y} r={NODE_RADIUS + 7}
              className="node-boundary" />}
            <circle cx={p.x} cy={p.y} r={NODE_RADIUS} className="node" />
            <text x={p.x} y={p.y} className="node-label" textAnchor="middle"
              dominantBaseline="middle">{s}</text>
          </g>
        )
      })}

      {hover && tById.get(hover) && (
        <g className="tooltip">
          <rect x={12} y={HEIGHT - 52} width={340} height={40} rx={6}
            className="tooltip-box" />
          <text x={24} y={HEIGHT - 36} className="tooltip-text">
            {(() => {
              const t = tById.get(hover)
              const u = usage.get(hover)
              return `${t.id} [${t.event_code}] ${t.source} → ${t.target}`
            })()}
          </text>
          <text x={24} y={HEIGHT - 20} className="tooltip-sub">
            {(() => {
              const u = usage.get(hover)
              if (!u) return '未出现在规范补全中'
              const parts = []
              if (u.inserted) parts.push(`漏记插入 ×${u.inserted}`)
              if (u.observed.length) parts.push(`消费观测 ${u.observed.join(', ')}`)
              return parts.join('；')
            })()}
          </text>
        </g>
      )}
    </svg>
  )
}
