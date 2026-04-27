import { useState, useEffect } from 'react'
import { Search, Loader2, AlertTriangle } from 'lucide-react'
import { useProject } from '../../context/ProjectContext'
import { pipelineExtract } from '../../api'
import ValidationGate from '../../components/ValidationGate'

export default function ExtractionStep() {
  const { state, dispatch } = useProject()
  const { project, placeholders, extractionResults, gates } = state
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [results, setResults] = useState(extractionResults)

  const confirmed = gates[2]

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
    dispatch({ type: 'CONFIRM_GATE', payload: 2 })
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
        <h3>Step 3 — Extraction Agent</h3>
        <p>Values are extracted from your connected sources for each placeholder.</p>
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
                      r.type === 'paragraph' ? (
                        <textarea
                          className="ex-value-input"
                          value={r.value || ''}
                          onChange={e => updateValue(i, e.target.value)}
                          rows={3}
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
                      <span className="ex-value-locked">{r.value || '—'}</span>
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
