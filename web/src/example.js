/** 文本按空白或逗号/分号切分为 token 列表。 */
export function parseTokens(text) {
  return text
    .split(/[\s,;]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

export const DEFAULT_EXAMPLE = {
  statesText: ['IDLE', 'PUMP_START', 'ROUGH_VAC', 'GATE_OPEN', 'COATING', 'DONE'].join('\n'),
  transitions: [
    { id: 'RP1', event_code: 'PUMP_ON', source: 'IDLE', target: 'PUMP_START' },
    { id: 'RP2', event_code: 'VAC_OK', source: 'PUMP_START', target: 'ROUGH_VAC' },
    { id: 'GV1', event_code: 'GATE_OPEN', source: 'ROUGH_VAC', target: 'GATE_OPEN' },
    { id: 'EV1', event_code: 'COAT', source: 'GATE_OPEN', target: 'COATING' },
    { id: 'FN1', event_code: 'FINISH', source: 'COATING', target: 'DONE' },
    // 成环：粗真空不足时泄压重来
    { id: 'VT0', event_code: 'VENT', source: 'ROUGH_VAC', target: 'IDLE' },
  ],
  initialState: 'IDLE',
  finalState: 'DONE',
  observationsText: ['VAC_OK', 'COAT', 'FINISH'].join('\n'),
}
