import { useEffect, useMemo, useState } from 'react'
import GraphView from './GraphView.jsx'
import { fetchHealth, solve } from './api.js'
import {
  SAMPLE,
  parseObservations,
  parseStates,
  parseTransitions,
  validateClient,
} from './model.js'
import './styles.css'

export default function App() {
  const [stateText, setStateText] = useState(SAMPLE.states.join(', '))
  const [transitionText, setTransitionText] = useState(SAMPLE.transitionText)
  const [start, setStart] = useState(SAMPLE.start)
  const [end, setEnd] = useState(SAMPLE.end)
  const [observationText, setObservationText] = useState(SAMPLE.observationText)

  const [result, setResult] = useState(null)
  const [serverError, setServerError] = useState(null)
  const [localProblems, setLocalProblems] = useState(null)
  const [loading, setLoading] = useState(false)
  const [health, setHealth] = useState({ state: 'checking', detail: '' })

  useEffect(() => {
    let alive = true
    const ping = () =>
      fetchHealth()
        .then((h) => alive && setHealth({ state: 'up', detail: h.version ?? '' }))
        .catch(() => alive && setHealth({ state: 'down', detail: '' }))
    ping()
    const t = setInterval(ping, 10000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  const states = useMemo(() => parseStates(stateText), [stateText])
  const parsedTransitions = useMemo(() => parseTransitions(transitionText), [transitionText])
  const observations = useMemo(() => parseObservations(observationText), [observationText])

  const counts = {
    states: states.length,
    transitions: parsedTransitions.rows.length,
    observations: observations.length,
  }

  async function runSolver() {
    setLoading(true)
    setServerError(null)
    setResult(null)
    const clientCheck = validateClient({
      states,
      transitions: parsedTransitions.rows,
      start: start.trim(),
      end: end.trim(),
      observations,
    })
    const parseProblems = parsedTransitions.errors.map((e) => `第 ${e.line} 行：${e.message}`)
    if (!clientCheck.ok || parseProblems.length) {
      setLocalProblems({ ...clientCheck.problems, transitions: [
        ...parseProblems,
        ...clientCheck.problems.transitions,
      ] })
      setLoading(false)
      return
    }
    setLocalProblems(null)
    const payload = {
      states,
      transitions: parsedTransitions.rows.map(({ line, ...rest }) => rest),
      start: start.trim(),
      end: end.trim(),
      observations,
    }
    const resp = await solve(payload)
    setLoading(false)
    if (resp.ok) {
      setResult(resp.data)
    } else {
      // Input content is intentionally left untouched so the user can fix it.
      setServerError(resp)
    }
  }

  const problemEntries = localProblems
    ? Object.entries(localProblems).filter(([, list]) => list.length)
    : []

  const failedObservation = serverError?.observationIndex ?? null

  return (
    <div className="page">
      <header className="app-header">
        <div className="title-row">
          <h1>真空镀膜设备 · 联锁日志漏记补全</h1>
          <span className={'health-badge ' + health.state}>
            {health.state === 'up'
              ? `API 在线${health.detail ? ' · v' + health.detail : ''}`
              : health.state === 'checking'
                ? 'API 探测中…'
                : 'API 不可达'}
          </span>
        </div>
        <p className="subtitle">
          按观测顺序为每个事件码指定唯一一条消费迁移，最小化漏记（插入）迁移数，
          并在全部最优解中取完整迁移标识序列字典序最小的规范解。
        </p>
      </header>

      <main className="layout">
        <section className="editor-pane">
          <Field
            label={`状态（2–80 个唯一 ASCII，当前 ${counts.states}）`}
            problems={localProblems?.states}
          >
            <textarea
              value={stateText}
              onChange={(e) => setStateText(e.target.value)}
              rows={3}
              spellCheck={false}
              aria-label="状态列表"
            />
          </Field>

          <Field
            label={`迁移（1–300 行：id, source, target, code；当前 ${counts.transitions}）`}
            problems={localProblems?.transitions}
          >
            <textarea
              value={transitionText}
              onChange={(e) => setTransitionText(e.target.value)}
              rows={10}
              spellCheck={false}
              aria-label="迁移列表"
              className="mono"
            />
          </Field>

          <div className="row-2">
            <Field label="初态" problems={localProblems?.endpoints}>
              <input value={start} onChange={(e) => setStart(e.target.value)} spellCheck={false} />
            </Field>
            <Field label="末态" problems={localProblems?.endpoints}>
              <input value={end} onChange={(e) => setEnd(e.target.value)} spellCheck={false} />
            </Field>
          </div>

          <Field
            label={`观测事件序列（1–200，保持顺序；当前 ${counts.observations}）`}
            problems={localProblems?.observations}
          >
            <ObservationEditor
              text={observationText}
              onChange={setObservationText}
              failedIndex={failedObservation}
              failedCode={serverError?.eventCode}
            />
          </Field>

          <div className="actions">
            <button className="primary" onClick={runSolver} disabled={loading}>
              {loading ? '求解中…' : '计算最优补全'}
            </button>
            <button
              onClick={() => {
                setStateText(SAMPLE.states.join(', '))
                setTransitionText(SAMPLE.transitionText)
                setStart(SAMPLE.start)
                setEnd(SAMPLE.end)
                setObservationText(SAMPLE.observationText)
                setResult(null)
                setServerError(null)
                setLocalProblems(null)
              }}
            >
              载入示例
            </button>
          </div>

          {problemEntries.length > 0 && (
            <div className="error-box" role="alert">
              <strong>输入非法，内容已保留：</strong>
              <ul>
                {problemEntries.flatMap(([field, list]) =>
                  list.map((msg, i) => <li key={field + i}>{msg}</li>),
                )}
              </ul>
            </div>
          )}

          {serverError && (
            <div className="error-box" role="alert">
              <strong>
                {serverError.code === 'unreachable'
                  ? '不存在可达补全，输入内容已保留：'
                  : `服务拒绝请求（${serverError.status ?? 'network'}），内容已保留：`}
              </strong>
              <div>{serverError.message}</div>
              {failedObservation != null && (
                <div className="locate">
                  已定位到第 <strong>{failedObservation}</strong> 个观测事件
                  {serverError.eventCode ? `（码 ${serverError.eventCode}）` : ''}，见上方高亮。
                </div>
              )}
            </div>
          )}

          {result && <ResultPanel result={result} />}
        </section>

        <section className="graph-pane">
          <GraphView
            states={states}
            transitions={parsedTransitions.rows.map(({ line, ...rest }) => rest)}
            start={start.trim()}
            end={end.trim()}
            result={result}
            failedBoundary={failedObservation}
          />
          <Legend />
        </section>
      </main>
    </div>
  )
}

function Field({ label, problems, children }) {
  return (
    <div className={'field' + (problems?.length ? ' has-error' : '')}>
      <label className="field-label">{label}</label>
      {children}
    </div>
  )
}

function ObservationEditor({ text, onChange, failedIndex, failedCode }) {
  const tokens = useMemo(() => parseObservations(text), [text])
  return (
    <div>
      <textarea
        value={text}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        spellCheck={false}
        aria-label="观测事件序列"
      />
      {tokens.length > 0 && (
        <div className="obs-chips" aria-hidden="false">
          {tokens.map((tok, i) => (
            <span
              key={i}
              className={
                'chip' +
                (failedIndex === i + 1 ? ' failed' : '')
              }
              title={`第 ${i + 1} 个观测`}
            >
              <b>{i + 1}</b> {tok}
            </span>
          ))}
          {failedIndex && failedCode && !tokens.includes(failedCode) && (
            <span className="chip failed">码 {failedCode} 无对应迁移</span>
          )}
        </div>
      )}
    </div>
  )
}

function ResultPanel({ result }) {
  return (
    <div className="result-box">
      <h2>规范解（字典序最小）</h2>
      <div className="metrics">
        <span>最少漏记迁移数：<strong>{result.inserted_count}</strong></span>
        <span>完整序列长度：<strong>{result.total_edge_count}</strong></span>
      </div>
      <ol className="sequence">
        {result.canonical_sequence.map((step, i) => (
          <li key={i} className={'step ' + step.role}>
            <span className="step-id">{step.edge_id}</span>
            <span className="step-route">
              {step.source} → {step.target}
            </span>
            <span className="step-code">{step.code}</span>
            <span className="step-role">
              {step.role === 'consumed'
                ? `消费观测 #${step.observation_index}`
                : '漏记插入'}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}

function Legend() {
  return (
    <div className="legend">
      <span><i className="swatch consumed" /> 消费观测的规范路径边</span>
      <span><i className="swatch inserted" /> 漏记插入的迁移</span>
      <span><i className="swatch mixed" /> 同一边在补全中既被插入又消费观测</span>
      <span><i className="swatch possible" /> 该边界下某最优补全可达状态</span>
      <span><i className="swatch normal" /> 未入选的迁移</span>
    </div>
  )
}
