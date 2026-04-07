import { useProject } from '../context/ProjectContext'
import StepProgressBar from '../components/StepProgressBar'
import TemplateStep from './steps/TemplateStep'
import ExtractionStep from './steps/ExtractionStep'
import MappingStep from './steps/MappingStep'
import ExportStep from './steps/ExportStep'

export default function PipelinePage() {
  const { state } = useProject()
  const { pipelineStep, gates, project } = state

  if (!project) return null

  const renderStep = () => {
    switch (pipelineStep) {
      case 0: return <TemplateStep />
      case 1: return <ExtractionStep />
      case 2: return <MappingStep />
      case 3: return <ExportStep />
      default: return <TemplateStep />
    }
  }

  return (
    <div className="pipeline-page">
      <div className="page-header">
        <h2>{project.name}</h2>
        {project.description && <p>{project.description}</p>}
      </div>

      <StepProgressBar currentStep={pipelineStep} gates={gates} />

      <div className="pipeline-step-container" key={pipelineStep}>
        {renderStep()}
      </div>
    </div>
  )
}
