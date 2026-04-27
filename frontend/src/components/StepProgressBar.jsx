import { FileText, Search, Map, Download, Check, Layers } from 'lucide-react'

const STEP_META = [
  { label: 'Pipelines', icon: Layers },
  { label: 'Template', icon: FileText },
  { label: 'Extraction', icon: Search },
  { label: 'Mapping', icon: Map },
  { label: 'Export', icon: Download },
]

export default function StepProgressBar({ currentStep, gates, onStepSelect }) {
  return (
    <div className="step-progress">
      {STEP_META.map((s, i) => {
        const Icon = s.icon
        const isActive = i === currentStep
        const isComplete = i < currentStep || (i < 4 && gates[i])
        const canNavigate = i <= currentStep || (i > 0 && gates[i - 1])
        return (
          <button
            key={i}
            type="button"
            className={`sp-step ${isActive ? 'active' : ''} ${isComplete ? 'complete' : ''} ${canNavigate ? 'clickable' : ''}`}
            onClick={() => canNavigate && onStepSelect && onStepSelect(i)}
            disabled={!canNavigate}
          >
            <div className="sp-dot">
              {isComplete ? <Check size={12} /> : <Icon size={14} />}
            </div>
            <span className="sp-label">{s.label}</span>
            {i < 4 && <div className={`sp-line ${isComplete ? 'complete' : ''}`} />}
          </button>
        )
      })}
    </div>
  )
}
