import { useProject } from '../context/ProjectContext'
import StepProgressBar from '../components/StepProgressBar'
import PipelineDetectionStep from './steps/PipelineDetectionStep'
import TemplateStep from './steps/TemplateStep'
import ExtractionStep from './steps/ExtractionStep'
import MappingStep from './steps/MappingStep'
import ExportStep from './steps/ExportStep'

export default function PipelinePage() {
  const { state, dispatch } = useProject()
  const { pipelineStep, gates, project } = state

  if (!project) return null

  const renderStep = () => {
    switch (pipelineStep) {
      case 0: return <PipelineDetectionStep />
      case 1: return <TemplateStep />
      case 2: return <ExtractionStep />
      case 3: return <MappingStep />
      case 4: return <ExportStep />
      default: return <PipelineDetectionStep />
    }
  }

  return (
    <div className="pipeline-page">
      <div className="page-header">
        <h2>{project.name}</h2>
        {project.description && <p>{project.description}</p>}
      </div>

      <StepProgressBar
        currentStep={pipelineStep}
        gates={gates}
        onStepSelect={(step) => dispatch({ type: 'SET_PIPELINE_STEP', payload: step })}
      />

      <div className="pipeline-step-container" key={pipelineStep}>
        {renderStep()}
      </div>
    </div>
  )
}
