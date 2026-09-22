/** 圆形布局 + 边路径（含双向边弧与自环）。 */

export function layoutCircle(states, width, height) {
  const cx = width / 2
  const cy = height / 2
  const r = Math.min(width, height) / 2 - 90
  const n = states.length
  const pos = {}
  states.forEach((s, i) => {
    const ang = n === 1 ? -Math.PI / 2 : -Math.PI / 2 + (2 * Math.PI * i) / n
    pos[s] = { x: cx + r * Math.cos(ang), y: cy + r * Math.sin(ang) }
  })
  return pos
}

const NODE_R = 26

export function edgeGeometry(pos, source, target, parallel = { slot: 0, total: 1 }) {
  const a = pos[source]
  const b = pos[target]
  if (source === target) {
    // 自环：多条平行自环绕节点错开
    const off = (parallel.slot - (parallel.total - 1) / 2) * 26
    const ax = a.x + off
    // 自环
    return {
      d: `M ${ax} ${a.y - NODE_R}
          C ${ax + 44} ${a.y - 58}, ${ax + 44} ${a.y + 6}, ${ax + 2} ${a.y + NODE_R - 4}`,
      labelX: ax + 52,
      labelY: a.y - 26,
      arrow: { x: ax + 2, y: a.y + NODE_R - 6, angle: 70 },
    }
  }
  const dx = b.x - a.x
  const dy = b.y - a.y
  const len = Math.hypot(dx, dy)
  const ux = dx / len
  const uy = dy / len
  // 起止收于节点圆边缘
  const sx = a.x + ux * NODE_R
  const sy = a.y + uy * NODE_R
  const tx = b.x - ux * (NODE_R + 7)
  const ty = b.y - uy * (NODE_R + 7)
  // 垂直方向弯曲，避免双向边重叠；同向平行边按 slot 错开
  const nx = -uy
  const ny = ux
  const spread = 46
  const bend =
    spread * (parallel.total === 1 ? 0.56 : 0.28 + (parallel.slot + 0.5) / parallel.total)
  const mx = (sx + tx) / 2 + nx * bend
  const my = (sy + ty) / 2 + ny * bend
  return {
    d: `M ${sx} ${sy} Q ${mx} ${my} ${tx} ${ty}`,
    labelX: (sx + tx) / 2 + nx * (bend + 12),
    labelY: (sy + ty) / 2 + ny * (bend + 12),
    arrow: { x: tx, y: ty, angle: (Math.atan2(ty - my, tx - mx) * 180) / Math.PI },
  }
}

export const NODE_RADIUS = NODE_R
