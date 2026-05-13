import { useState, useEffect } from 'react'
import { Search, Loader2, AlertTriangle, RefreshCw, Pencil, Table2 } from 'lucide-react'
import { useProject } from '../../context/ProjectContext'
import { pipelineExtract } from '../../api'
import ValidationGate from '../../components/ValidationGate'

/* ── Parse a table value (JSON array, Python-dict-like, or markdown) → rows ── */
function parseTableValue(val) {
  if (!val || val === '—') return null
  const raw = val.trim()

  // 1. Try direct JSON array
  try {
    const rows = JSON.parse(raw)
    if (Array.isArray(rows) && rows.length > 0 && typeof rows[0] === 'object') return rows
  } catch (_) {}

  // 2. Try Python-dict-like: carefully replace only structural single quotes
  //    (quotes that delimit keys/values, not quotes inside values)
  try {
    // Replace single-quoted strings that are dict keys/values but preserve inner single quotes
    // Strategy: use a state-machine-style replace instead of naive global replace
    let json = ''
    let i = 0
    while (i < raw.length) {
      if (raw[i] === "'") {
        // Find matching closing single quote, allowing \' escapes
        let j = i + 1
        let content = ''
        while (j < raw.length) {
          if (raw[j] === '\\' && raw[j + 1] === "'") { content += "'"; j += 2 }
          else if (raw[j] === "'") { j++; break }
          else { content += raw[j]; j++ }
        }
        // Escape any double quotes in content, then wrap in double quotes
        json += '"' + content.replace(/"/g, '\\"') + '"'
        i = j
      } else {
        json += raw[i]
        i++
      }
    }
    const rows = JSON.parse(json)
    if (Array.isArray(rows) && rows.length > 0 && typeof rows[0] === 'object') return rows
  } catch (_) {}

  // 3. Try markdown table (| col | col |)
  const lines = raw.split('\n').filter(l => l.trim().startsWith('|'))
  if (lines.length >= 2) {
    const parseRow = line => line.split('|').map(c => c.trim()).filter((_, i, a) => i > 0 && i < a.length - 1)
    const headers = parseRow(lines[0])
    return lines.slice(2).map(line => {
      const cells = parseRow(line)
      return Object.fromEntries(headers.map((h, i) => [h, cells[i] ?? '']))
    })
  }

  return null
}

/* ── Rendered table component ── */
function RenderedTable({ val }) {
  const rows = parseTableValue(val)
  if (!rows) return <span className="ex-value-locked">{val || '—'}</span>
  // Union of all keys across all rows so no column is lost if row[0] is missing a key
  const headersSet = new Set()
  rows.forEach(r => Object.keys(r).forEach(k => headersSet.add(k)))
  const headers = Array.from(headersSet)
  return (
    <div className="ex-table-rendered">
      <table>
        <thead><tr>{headers.map((h, i) => <th key={i}>{h}</th>)}</tr></thead>
        <tbody>{rows.map((row, i) => (
          <tr key={i}>{headers.map((h, j) => (
            <td key={j}>
              {String(row[h] ?? '').includes('\n')
                ? <pre className="ex-sql-snippet">{row[h]}</pre>
                : row[h] ?? ''}
            </td>
          ))}</tr>
        ))}</tbody>
      </table>
    </div>
  )
}

/* ── Render helpers for locked/confirmed view ── */
function renderLockedValue(r) {
  const val = r.value || '—'

  if (r.type === 'table') return <RenderedTable val={val} />

  if (r.type === 'list') {
    const items = val.split('\n').filter(l => l.trim().startsWith('-')).map(l => l.replace(/^-\s*/, '').trim())
    if (items.length > 0) {
      return <ul className="ex-list-rendered">{items.map((item, i) => <li key={i}>{item}</li>)}</ul>
    }
  }

  return <span className="ex-value-locked">{val}</span>
}

export default function ExtractionStep() {
  const { state, dispatch } = useProject()
  const { project, placeholders, extractionResults, gates } = state
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [results, setResults] = useState(extractionResults)
  const [tableEditIndices, setTableEditIndices] = useState(new Set())

  const toggleTableEdit = (idx) => {
    setTableEditIndices(prev => {
      const next = new Set(prev)
      next.has(idx) ? next.delete(idx) : next.add(idx)
      return next
    })
  }

  const confirmed = gates[1]

  // Auto-run extraction on mount if not yet done
  useEffect(() => {
    if (results.length === 0 && !loading && placeholders.length > 0) {
      runExtraction()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const runExtraction = async () => {
    if (!project) return
    setLoading(true)
    setError(null)
    try {
      const res = await pipelineExtract(project.id, placeholders)
      setResults(res.data.results || [])
      dispatch({ type: 'SET_EXTRACTION_RESULTS', payload: res.data.results || [] })
    } catch (err) {
      setError(err.response?.data?.detail || 'Extraction failed.')
    }
    setLoading(false)
  }

  const updateValue = (idx, value) => {
    const updated = [...results]
    updated[idx] = { ...updated[idx], value }
    setResults(updated)
    dispatch({ type: 'SET_EXTRACTION_RESULTS', payload: updated })
  }

  const handleConfirm = () => {
    const values = {}
    results.forEach(r => { values[r.id] = r.value })
    dispatch({ type: 'SET_CONFIRMED_VALUES', payload: values })
    dispatch({ type: 'CONFIRM_GATE', payload: 1 })
  }

  const filledCount = results.filter(r => r.value && r.confidence !== 'low').length
  const lowCount = results.filter(r => r.confidence === 'low').length
  const medCount = results.filter(r => r.confidence === 'medium').length

  const gateItems = [
    { text: `${filledCount} value${filledCount !== 1 ? 's' : ''} extracted (high confidence)`, status: 'ok' },
    ...(medCount > 0 ? [{ text: `${medCount} medium confidence`, status: 'warn' }] : []),
    ...(lowCount > 0 ? [{ text: `${lowCount} low confidence / missing`, status: 'error' }] : []),
  ]

  return (
    <div className="pipeline-step">
      <div className="ps-header">
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem' }}>
          <div>
            <h3>Step 2 — Extraction Agent</h3>
            <p>Values are extracted from your connected sources for each placeholder.</p>
          </div>
          {!loading && (
            <button
              className="btn btn-secondary"
              onClick={() => { dispatch({ type: 'UNCONFIRM_GATE', payload: 1 }); runExtraction() }}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', whiteSpace: 'nowrap', flexShrink: 0 }}
            >
              <RefreshCw size={14} />
              Re-extract
            </button>
          )}
        </div>
      </div>

      {error && <div className="message error">{error}</div>}

      {loading && (
        <div className="loading">
          <div className="spinner" />
          <span>Extracting values from sources… (this may take a minute)</span>
        </div>
      )}

      {!loading && results.length > 0 && (
        <div className="extraction-panel">
          <table className="ex-table">
            <thead>
              <tr>
                <th>Placeholder</th>
                <th>Extracted Value</th>
                <th>Source</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={r.id} className={`conf-${r.confidence} ${confirmed ? 'locked' : ''}`}>
                  <td>
                    <div className="ex-ph-label">{r.label}</div>
                    {r.section && <div className="ex-ph-section">{r.section}</div>}
                  </td>
                  <td>
                    {!confirmed ? (
                      r.type === 'table' ? (
                        <div>
                          {tableEditIndices.has(i) ? (
                            <textarea
                              className="ex-value-input"
                              value={r.value || ''}
                              onChange={e => updateValue(i, e.target.value)}
                              rows={6}
                            />
                          ) : (
                            <RenderedTable val={r.value || ''} />
                          )}
                          <button
                            className="btn-text ex-table-toggle"
                            onClick={() => toggleTableEdit(i)}
                          >
                            {tableEditIndices.has(i)
                              ? <><Table2 size={12} /> View table</>
                              : <><Pencil size={12} /> Edit raw</>}
                          </button>
                        </div>
                      ) : (r.type === 'paragraph' || r.type === 'list') ? (
                        <textarea
                          className="ex-value-input"
                          value={r.value || ''}
                          onChange={e => updateValue(i, e.target.value)}
                          rows={r.type === 'list' ? 4 : 3}
                        />
                      ) : (
                        <input
                          className="ex-value-input"
                          type="text"
                          value={r.value || ''}
                          onChange={e => updateValue(i, e.target.value)}
                        />
                      )
                    ) : (
                      renderLockedValue(r)
                    )}
                  </td>
                  <td className="ex-source">{r.source}</td>
                  <td>
                    <span className={`conf-badge ${r.confidence}`}>
                      {r.confidence === 'low' && <AlertTriangle size={11} />}
                      {r.confidence}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && results.length > 0 && (
        <ValidationGate
          title="Validation Gate 3 — Confirm Extracted Values"
          summary={`${filledCount} of ${results.length} values filled.`}
          items={gateItems}
          confirmed={confirmed}
          buttonLabel="Confirm Extracted Values"
          onConfirm={handleConfirm}
        />
      )}
    </div>
  )
}
