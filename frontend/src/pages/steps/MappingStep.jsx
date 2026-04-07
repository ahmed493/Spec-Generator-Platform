import { useState, useEffect } from 'react'
import { Map, Loader2, Eye } from 'lucide-react'
import { useProject } from '../../context/ProjectContext'
import { pipelineMap } from '../../api'
import ValidationGate from '../../components/ValidationGate'

export default function MappingStep() {
  const { state, dispatch } = useProject()
  const { project, confirmedValues, placeholders, spec, validation, gates } = state
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [editableSpec, setEditableSpec] = useState(spec)
  const [hoveredPlaceholder, setHoveredPlaceholder] = useState(null)

  const confirmed = gates[2]

  useEffect(() => {
    if (!spec && !loading && Object.keys(confirmedValues).length > 0) {
      runMapping()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setEditableSpec(spec)
  }, [spec])

  const runMapping = async () => {
    if (!project) return
    setLoading(true)
    setError(null)
    try {
      const res = await pipelineMap(project.id, confirmedValues)
      dispatch({ type: 'SET_SPEC', payload: { spec: res.data.spec, validation: res.data.validation } })
    } catch (err) {
      setError(err.response?.data?.detail || 'Mapping failed.')
    }
    setLoading(false)
  }

  const handleConfirm = () => {
    dispatch({ type: 'SET_SPEC', payload: { spec: editableSpec, validation } })
    dispatch({ type: 'CONFIRM_GATE', payload: 2 })
  }

  const gapCount = Object.values(confirmedValues).filter(
    v => !v || v.toLowerCase() === 'non identifié'
  ).length

  const gateItems = [
    { text: `${placeholders.length} placeholders mapped`, status: 'ok' },
    ...(validation?.is_valid ? [{ text: 'All required fields filled', status: 'ok' }] : []),
    ...(gapCount > 0 ? [{ text: `${gapCount} gap${gapCount > 1 ? 's' : ''} remaining`, status: 'warn' }] : []),
    ...(validation?.warnings?.length > 0
      ? [{ text: `${validation.warnings.length} warning${validation.warnings.length > 1 ? 's' : ''}`, status: 'warn' }]
      : []),
  ]

  return (
    <div className="pipeline-step">
      <div className="ps-header">
        <h3>Step 3 — Mapping Agent</h3>
        <p>Values are mapped into the template. Review and edit the live preview below.</p>
      </div>

      {error && <div className="message error">{error}</div>}

      {loading && (
        <div className="loading">
          <div className="spinner" />
          <span>Composing specification from template + extracted values…</span>
        </div>
      )}

      {!loading && editableSpec && (
        <div className="mapping-panel">
          {/* Inline placeholder legend */}
          <div className="mp-legend">
            <Eye size={14} />
            <span>Hover any highlighted value to see the original placeholder it replaced.</span>
          </div>

          {/* Live spec preview — editable textarea with highlighting */}
          <div className="mp-preview-wrap">
            <textarea
              className="mp-preview"
              value={editableSpec}
              onChange={e => !confirmed && setEditableSpec(e.target.value)}
              readOnly={confirmed}
              rows={Math.max(20, editableSpec.split('\n').length)}
            />
          </div>

          {/* Value diff sidebar */}
          <div className="mp-values-sidebar">
            <h4>Filled Values</h4>
            {placeholders.map(ph => {
              const val = confirmedValues[ph.id]
              const isMissing = !val || val.toLowerCase() === 'non identifié'
              return (
                <div key={ph.id}
                  className={`mp-val-item ${isMissing ? 'missing' : ''} ${hoveredPlaceholder === ph.id ? 'hovered' : ''}`}
                  onMouseEnter={() => setHoveredPlaceholder(ph.id)}
                  onMouseLeave={() => setHoveredPlaceholder(null)}>
                  <div className="mp-val-ph">{ph.label}</div>
                  <div className="mp-val-filled">{val || '—'}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {!loading && editableSpec && (
        <ValidationGate
          title="Validation Gate 3 — Approve Spec"
          summary={validation?.is_valid
            ? 'All required fields are filled. The specification is ready.'
            : `Validation report: ${validation?.report || 'No report'}`}
          items={gateItems}
          confirmed={confirmed}
          buttonLabel="Approve Spec"
          onConfirm={handleConfirm}
        />
      )}
    </div>
  )
}
