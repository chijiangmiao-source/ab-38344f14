// 临时冒烟：服务端渲染 GraphSvg，覆盖布局/平行边/边界高亮等运行时逻辑。
import React from 'react'
import { renderToString } from 'react-dom/server'
import GraphSvg from '../src/GraphSvg.jsx'

const states = ['A', 'B', 'C', 'F']
const transitions = [
  { id: 'a', event_code: 'X', source: 'A', target: 'B' },
  { id: 'a2', event_code: 'X', source: 'A', target: 'B' }, // 同向平行边
  { id: 'loop', event_code: 'EV', source: 'B', target: 'A' },
  { id: 'b', event_code: 'Y', source: 'A', target: 'C' },
  { id: 'self', event_code: 'S', source: 'C', target: 'C' },
  { id: 'done', event_code: 'D', source: 'C', target: 'F' },
]
const result = {
  canonical_sequence: ['a', 'loop', 'b', 'self', 'done'],
  canonical_events: [null, 1, null, null, 2],
  boundary_states: [['A'], ['A'], ['F']],
}

const html = renderToString(
  React.createElement(GraphSvg, {
    states,
    transitions,
    result,
    selectedBoundary: 1,
  }),
)
const needed = ['<svg', 'node-boundary', 'edge-inserted', 'edge-observed', 'edge-code', 'EV</tspan']
for (const token of needed) {
  if (!html.includes(token)) {
    console.error('missing token in render:', token)
    process.exit(1)
  }
}
// 无边界选中时不应渲染 boundary 圈
const html2 = renderToString(
  React.createElement(GraphSvg, { states, transitions, result, selectedBoundary: 99 }),
)
if (html2.includes('node-boundary')) {
  console.error('boundary ring rendered with invalid selection')
  process.exit(1)
}
console.log('GraphSvg SSR smoke OK, svg bytes =', html.length)
