import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchLimits, solve } from './api'
import { parseTokens, DEFAULT_EXAMPLE } from './example'
import GraphSvg from './GraphSvg'

const emptyTransition = () => ({ id: '', event_code: '', source: '', target: '' })

export default function App() {
  const [limits, setLimits] = useState(null)
  const [statesText, setStatesText] = useState(DEFAULT_EXAMPLE.statesText)
  const [transitions, setTransitions] = useState(DEFAULT_EXAMPLE.transitions)
  const [initialState, setInitialState] = useState(DEFAULT_EXAMPLE.initialState)
  const [finalState, setFinalState] = useState(DEFAULT_EXAMPLE.finalState)
  const [observationsText, setObservationsText] = useState(DEFAULT_EXAMPLE.observationsText)

  const [result, setResult] = useState(null)
  const [unreachable, setUnreachable] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [boundaryIdx, setBoundaryIdx] = useState(0)
  const transitionRefs = useRef([])

  useEffect(() => {
    fetchLimits().then(setLimits).catch(() => setLimits(null))
  }, [])

  const states = useMemo(() => parseTokens(statesText), [statesText])
  const observations = useMemo(() => parseTokens(observationsText), [observationsText])

  function updateTransition(i, patch) {
    setTransitions((ts) => ts.map((t, j) => (j === i ? { ...t, ...patch } : t)))
  }
  function addTransition() {
    setTransitions((ts) => [...ts, emptyTransition()])
  }
  function removeTransition(i) {
    setTransitions((ts) => ts.filter((_, j) => j !== i))
  }

  function locateError(err) {
    if (err?.field === 'transitions' && typeof err.index === 'number') {
      transitionRefs.current[err.index]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }

  async function onSolve() {
    setLoading(true)
    setError(null)
    setUnreachable(null)
    setResult(null)
    const payload = {
      states,
      transitions: transitions.map((t) => ({
        id: t.id.trim(),
        event_code: t.event_code.trim(),
        source: t.source.trim(),
        target: t.target.trim(),
      })),
      initial_state: initialState.trim(),
      final_state: finalState.trim(),
      observations,
    }
    try {
      const { status, data } = await solve(payload)
      if (status === 200 && data?.ok && data.feasible) {
        setResult(data)
        setBoundaryIdx(0)
      } else if (status === 200 && data?.ok && data.feasible === false) {
        setUnreachable(data.reason || '不存在可达补全。')
      } else {
        const err = data?.error || { message: `请求失败（HTTP ${status}），输入内容已保留。` }
        setError(err)
        locateError(err)
      }
    } catch (e) {
      setError({ message: `网络错误：${e.message}；输入内容已保留。` })
    } finally {
      setLoading(false)
    }
  }

  function loadExample() {
    setStatesText(DEFAULT_EXAMPLE.statesText)
    setTransitions(DEFAULT_EXAMPLE.transitions.map((t) => ({ ...t })))
    setInitialState(DEFAULT_EXAMPLE.initialState)
    setFinalState(DEFAULT_EXAMPLE.finalState)
    setObservationsText(DEFAULT_EXAMPLE.observationsText)
    setResult(null)
    setUnreachable(null)
    setError(null)
  }

  const rowInvalid = (i) => error?.field === 'transitions' && error.index === i

  return (
    <div className="app">
      <header className="app-header">
        <h1>真空镀膜联锁日志 · 漏记迁移补全</h1>
        <p className="subtitle">
          最小化插入的漏记迁移数 · 字典序最小规范解 · 各观测边界可能状态集合
        </p>
      </header>

      <main className="layout">
        <section className="panel editor">
          <h2>输入</h2>

          <label className="field">
            <span className="field-label">
              状态（{states.length}/{limits?.max_states ?? 80}，空白或逗号分隔，ASCII 唯一）
            </span>
            <textarea
              value={statesText}
              onChange={(e) => setStatesText(e.target.value)}
              rows={5}
              spellCheck={false}
              className={error?.field === 'states' ? 'invalid' : ''}
              placeholder="IDLE&#10;PUMPING&#10;..."
            />
          </label>

          <div className="field">
            <div className="field-label-row">
              <span className="field-label">
                有向迁移（{transitions.length}/{limits?.max_transitions ?? 300}，
                标识唯一，可成环、同码多边）
              </span>
              <button type="button" className="btn-small" onClick={addTransition}>
                + 添加迁移
              </button>
            </div>
            <div className="trans-table">
              <div className="trans-row trans-head">
                <span>标识</span><span>事件码</span><span>源状态</span><span>目标状态</span><span></span>
              </div>
              {transitions.map((t, i) => (
                <div
                  className={'trans-row' + (rowInvalid(i) ? ' row-invalid' : '')}
                  key={i}
                  ref={(el) => (transitionRefs.current[i] = el)}
                >
                  <input value={t.id} onChange={(e) => updateTransition(i, { id: e.target.value })}
                    spellCheck={false} placeholder="RP1" />
                  <input value={t.event_code}
                    onChange={(e) => updateTransition(i, { event_code: e.target.value })}
                    spellCheck={false} placeholder="PUMP_ON" />
                  <input value={t.source}
                    onChange={(e) => updateTransition(i, { source: e.target.value })}
                    spellCheck={false} list="state-list" placeholder="IDLE" />
                  <input value={t.target}
                    onChange={(e) => updateTransition(i, { target: e.target.value })}
                    spellCheck={false} list="state-list" placeholder="VAC_OK" />
                  <button type="button" className="btn-del" onClick={() => removeTransition(i)}
                    aria-label="删除该行">×</button>
                </div>
              ))}
            </div>
            <datalist id="state-list">
              {states.map((s) => <option key={s} value={s} />)}
            </datalist>
          </div>

          <div className="two-col">
            <label className="field">
              <span className="field-label">初态</span>
              <input value={initialState} onChange={(e) => setInitialState(e.target.value)}
                spellCheck={false} list="state-list"
                className={error?.field === 'initial_state' ? 'invalid' : ''} />
            </label>
            <label className="field">
              <span className="field-label">末态</span>
              <input value={finalState} onChange={(e) => setFinalState(e.target.value)}
                spellCheck={false} list="state-list"
                className={error?.field === 'final_state' ? 'invalid' : ''} />
            </label>
          </div>

          <label className="field">
            <span className="field-label">
              观测事件序列（{observations.length}/{limits?.max_observations ?? 200}，保持顺序）
            </span>
            <textarea
              value={observationsText}
              onChange={(e) => setObservationsText(e.target.value)}
              rows={3}
              spellCheck={false}
              className={error?.field === 'observations' ? 'invalid' : ''}
              placeholder="VAC_OK&#10;COAT&#10;FINISH"
            />
          </label>

          <div className="actions">
            <button type="button" className="btn-primary" onClick={onSolve} disabled={loading}>
              {loading ? '求解中…' : '求解'}
            </button>
            <button type="button" className="btn-ghost" onClick={loadExample}>
              载入示例
            </button>
          </div>

          {error && (
            <div className="alert alert-error" role="alert">
              <strong>输入非法{typeof error.index === 'number' ? `（第 ${error.index + 1} 行迁移）` : ''}：
              </strong> {error.message}
            </div>
          )}
          {unreachable && (
            <div className="alert alert-warn" role="alert">
              <strong>无可达补全：</strong> {unreachable}
              <div className="alert-hint">输入内容已保留，可调整后重新求解。</div>
            </div>
          )}
        </section>

        <section className="panel result">
          <h2>结果</h2>
          {!result && !unreachable && !error && (
            <p className="placeholder">编辑左侧输入后点击「求解」。绿色边为消费观测的迁移，
              红色边为漏记插入的迁移。</p>
          )}
          {result && (
            <>
              <div className="stat-row">
                <div className="stat">
                  <div className="stat-num">{result.inserted_count}</div>
                  <div className="stat-label">最少漏记插入</div>
                </div>
                <div className="stat">
                  <div className="stat-num">{result.canonical_sequence.length}</div>
                  <div className="stat-label">完整序列长度</div>
                </div>
              </div>

              <h3>规范路径（字典序最小）</h3>
              <ol className="seq-list">
                {result.canonical_sequence.map((id, i) => {
                  const ev = result.canonical_events[i]
                  return (
                    <li key={i} className={ev == null ? 'step step-inserted' : 'step step-observed'}>
                      <span className="step-id">{id}</span>
                      {ev == null
                        ? <span className="step-tag tag-inserted">漏记插入</span>
                        : <span className="step-tag tag-observed">观测 #{ev}</span>}
                    </li>
                  )
                })}
              </ol>

              <h3>状态迁移图（SVG）</h3>
              <GraphSvg
                states={result.states}
                transitions={result.transitions}
                result={result}
                selectedBoundary={boundaryIdx}
              />
              <div className="legend">
                <span><i className="sw sw-obs" /> 消费观测</span>
                <span><i className="sw sw-ins" /> 漏记插入</span>
                <span><i className="sw sw-both" /> 既消费又插入</span>
                <span><i className="sw sw-idle" /> 未使用</span>
              </div>

              <h3>观测边界可能状态（全部最优补全）</h3>
              <div className="boundary-controls">
                <button type="button" onClick={() => setBoundaryIdx((v) => Math.max(0, v - 1))}
                  disabled={boundaryIdx === 0}>‹</button>
                <span className="boundary-label">
                  {boundaryIdx === 0
                    ? '边界 0 · 初态前'
                    : `边界 ${boundaryIdx} · 消费观测 #${boundaryIdx} 后`}
                </span>
                <button type="button"
                  onClick={() => setBoundaryIdx((v) => Math.min(result.boundary_states.length - 1, v + 1))}
                  disabled={boundaryIdx >= result.boundary_states.length - 1}>›</button>
              </div>
              <div className="boundary-states">
                {result.boundary_states[boundaryIdx]?.map((s) => (
                  <span key={s} className="state-chip">{s}</span>
                ))}
              </div>
            </>
          )}
        </section>
      </main>

      <footer className="app-footer">
        迁移可成环 · 同事件码可出现在多条边 · 展开图 (i, 状态) 上精确最短路径求解
      </footer>
    </div>
  )
}
