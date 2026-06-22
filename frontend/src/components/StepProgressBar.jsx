import { GitBranch, Search, Map, Download, Check, Layers } from 'lucide-react'

const STEP_META = [
  { label: 'Pipelines',  icon: Layers    },
  { label: 'Extraction', icon: Search    },
  { label: 'Mapping',    icon: Map       },
  { label: 'Diagram',    icon: GitBranch },
  { label: 'Export',     icon: Download  },
]

/* SVG gradient def shared by all rings */
const RingGradDef = () => (
  <svg className="jw-svg-defs" aria-hidden="true">
    <defs>
      <linearGradient id="jwRingGrad" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%"   stopColor="#FF2D78" />
        <stop offset="100%" stopColor="#FF6B00" />
      </linearGradient>
    </defs>
  </svg>
)

export default function StepProgressBar({ currentStep, gates, onStepSelect }) {
  return (
    <>
      <RingGradDef />
      <div className="step-progress">
        {STEP_META.map((s, i) => {
          const Icon = s.icon
          const isActive   = i === currentStep
          const isComplete = i < currentStep || (i < 4 && gates[i])
          const canNavigate = i <= currentStep || (i > 0 && gates[i - 1])
          return (
            <button
              key={i}
              type="button"
              className={[
                'sp-step',
                isActive   ? 'active'    : '',
                isComplete ? 'complete'  : '',
                canNavigate ? 'clickable' : '',
              ].filter(Boolean).join(' ')}
              onClick={() => canNavigate && onStepSelect && onStepSelect(i)}
              disabled={!canNavigate}
              aria-label={`${s.label} step${isComplete ? ' (complete)' : isActive ? ' (active)' : ''}`}
            >
              <div className="sp-dot">
                {isComplete ? <Check size={14} /> : <Icon size={14} />}
              </div>
              <span className="sp-label">{s.label}</span>
              {i < 4 && <div className={`sp-line ${isComplete ? 'complete' : ''}`} />}
            </button>
          )
        })}
      </div>
    </>
  )
}
