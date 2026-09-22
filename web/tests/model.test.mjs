import test from 'node:test'
import assert from 'node:assert/strict'

import {
  parseStates,
  parseObservations,
  parseTransitions,
  validateClient,
} from '../src/model.js'

test('parseStates handles comma/space/newline separators', () => {
  assert.deepEqual(parseStates('A, B C\nD;E'), ['A', 'B', 'C', 'D', 'E'])
  assert.deepEqual(parseStates('  \n '), [])
})

test('parseObservations preserves order', () => {
  assert.deepEqual(parseObservations('x, y x\ny'), ['x', 'y', 'x', 'y'])
})

test('parseTransitions accepts 4-column rows and flags malformed lines', () => {
  const text = [
    '# comment line',
    'e1, A, B, x',
    'e2\tA\tC\ty',
    'bad row only two',
  ].join('\n')
  const { rows, errors } = parseTransitions(text)
  assert.equal(rows.length, 2)
  assert.deepEqual(rows[0], { id: 'e1', source: 'A', target: 'B', code: 'x', line: 2 })
  assert.equal(errors.length, 1)
  assert.equal(errors[0].line, 4)
})

test('validateClient accepts a well-formed case', () => {
  const result = validateClient({
    states: ['A', 'B'],
    transitions: [{ id: 'e1', source: 'A', target: 'B', code: 'x', line: 1 }],
    start: 'A',
    end: 'B',
    observations: ['x'],
  })
  assert.equal(result.ok, true)
})

test('validateClient reports duplicates, undeclared states and limits', () => {
  const result = validateClient({
    states: ['A', 'A'],
    transitions: [
      { id: 'e1', source: 'A', target: 'Z', code: 'x', line: 1 },
      { id: 'e1', source: 'A', target: 'A', code: 'λ', line: 2 },
    ],
    start: 'Q',
    end: 'B',
    observations: [],
  })
  assert.equal(result.ok, false)
  assert.ok(result.problems.states.some((m) => m.includes('重复')))
  assert.ok(result.problems.transitions.some((m) => m.includes('Z')))
  assert.ok(result.problems.transitions.some((m) => m.includes('重复')))
  assert.ok(result.problems.transitions.some((m) => m.includes('非法')))
  assert.ok(result.problems.endpoints.some((m) => m.includes('Q')))
  assert.ok(result.problems.observations.some((m) => m.includes('至少')))
})

test('validateClient enforces the 80 / 300 / 200 upper bounds', () => {
  const states = Array.from({ length: 81 }, (_, i) => `S${i}`)
  const transitions = Array.from({ length: 301 }, (_, i) => ({
    id: `t${i}`, source: 'S0', target: 'S1', code: 'x', line: i + 1,
  }))
  const result = validateClient({
    states,
    transitions,
    start: 'S0',
    end: 'S1',
    observations: Array.from({ length: 201 }, () => 'x'),
  })
  assert.equal(result.ok, false)
  assert.ok(result.problems.states.some((m) => m.includes('80')))
  assert.ok(result.problems.transitions.some((m) => m.includes('300')))
  assert.ok(result.problems.observations.some((m) => m.includes('200')))
})
