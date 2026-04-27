import { CheckCircle, Lock } from 'lucide-react'

export default function ValidationGate({ title, summary, items, onConfirm, confirmed, buttonLabel = 'Confirm & Continue', disabled = false }) {
  return (
    <div className={`validation-gate ${confirmed ? 'confirmed' : ''}`}>
      <div className="vg-frost" />
      <div className="vg-content">
        <div className="vg-header">
          {confirmed
            ? <CheckCircle size={20} className="vg-icon confirmed" />
            : <Lock size={20} className="vg-icon locked" />}
          <h3 className="vg-title">{title}</h3>
        </div>
        {summary && <p className="vg-summary">{summary}</p>}
        {items && items.length > 0 && (
          <ul className="vg-items">
            {items.map((item, i) => (
              <li key={i} className={`vg-item ${item.status || ''}`}>{item.text}</li>
            ))}
          </ul>
        )}
        {!confirmed && (
          <button className="btn btn-primary vg-btn" onClick={onConfirm} disabled={disabled}>
            <CheckCircle size={14} />
            {buttonLabel}
          </button>
        )}
        {confirmed && (
          <span className="vg-confirmed-label">
            <CheckCircle size={14} /> Confirmed
          </span>
        )}
      </div>
    </div>
  )
}
