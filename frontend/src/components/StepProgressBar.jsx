import { FileText, Search, Map, Download, Check } from 'lucide-react'

const STEP_META = [
  { label: 'Template', icon: FileText },
  { label: 'Extraction', icon: Search },
  { label: 'Mapping', icon: Map },
  { label: 'Export', icon: Download },
]

export default function StepProgressBar({ currentStep, gates }) {
  return (
    <div className="step-progress">
      {STEP_META.map((s, i) => {
        const Icon = s.icon
        const isActive = i === currentStep
        const isComplete = i < currentStep || (i < 3 && gates[i])
        return (
          <div key={i} className={`sp-step ${isActive ? 'active' : ''} ${isComplete ? 'complete' : ''}`}>
            <div className="sp-dot">
              {isComplete ? <Check size={12} /> : <Icon size={14} />}
            </div>
            <span className="sp-label">{s.label}</span>
            {i < 3 && <div className={`sp-line ${isComplete ? 'complete' : ''}`} />}
          </div>
        )
      })}
    </div>
  )
}
