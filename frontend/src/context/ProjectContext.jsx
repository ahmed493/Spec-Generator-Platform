import { createContext, useContext, useReducer, useCallback } from 'react'
import { getProject } from '../api'

const ProjectContext = createContext(null)

const STEPS = ['pipelines', 'extraction', 'mapping', 'diagram', 'export']

const initialState = {
  // Navigation
  currentPage: 'projects',    // projects | connections | pipeline
  // Active project
  project: null,
  projectId: null,
  // Pipeline
  pipelineStep: 0,            // 0-4 index into STEPS
  gates: [false, false, false, false], // confirmed flags for gates 0-3
  // Pipeline detection (step 0)
  detectedPipelines: [],
  selectedPipeline: null,     // the pipeline dict the user chose
  // Template — set at project level BEFORE launching pipeline
  templateReady: false,
  templateTitle: '',
  placeholders: [],
  // Extraction (step 1)
  extractionResults: [],
  confirmedValues: {},
  // Mapping / Diagram / Export (steps 2-4)
  spec: '',
  validation: null,
  specVersions: [],
  approvedVersionId: null,
  diagramCode: '',
  // Chat
  chatOpen: false,
  chatHistory: [],
}

function reducer(state, action) {
  switch (action.type) {
    case 'SET_PAGE':
      return { ...state, currentPage: action.payload }
    case 'OPEN_PROJECT':
      return {
        ...state,
        currentPage: 'pipeline',
        project: action.payload,
        projectId: action.payload.id,
        pipelineStep: 0,
        gates: [false, false, false, false],
        detectedPipelines: [],
        selectedPipeline: null,
        // Template kept — configured at project level before launch
        extractionResults: [],
        confirmedValues: {},
        spec: '',
        validation: null,
        specVersions: [],
        approvedVersionId: null,
        diagramCode: '',
        chatHistory: [],
      }
    case 'SET_PROJECT':
      return { ...state, project: action.payload }
    case 'CLOSE_PROJECT':
      return { ...initialState, currentPage: 'projects' }
    // Set template at project level (in ProjectWorkspace, before pipeline launch)
    case 'SET_PROJECT_TEMPLATE':
      return {
        ...state,
        templateTitle: action.payload.template_title || '',
        placeholders: action.payload.placeholders || [],
        templateReady: true,
      }
    // Clear template when switching projects
    case 'CLEAR_PROJECT_TEMPLATE':
      return { ...state, templateTitle: '', placeholders: [], templateReady: false }

    // Pipeline
    case 'SET_PIPELINE_STEP':
      return { ...state, pipelineStep: action.payload }
    // Load a pipeline (or merged set) from the catalog, skip detection, go to extraction
    case 'LOAD_FROM_CATALOG': {
      const { project, pipelines, selectedPipeline } = action.payload
      return {
        ...state,
        currentPage: 'pipeline',
        project,
        projectId: project.id,
        pipelineStep: 1,
        gates: [true, false, false, false],
        detectedPipelines: pipelines,
        selectedPipeline,
        // Template kept — configured at project level before launch
        extractionResults: [],
        confirmedValues: {},
        spec: '',
        validation: null,
        specVersions: [],
        approvedVersionId: null,
        diagramCode: '',
        chatHistory: [],
      }
    }
    case 'SET_DETECTED_PIPELINES':
      return { ...state, detectedPipelines: action.payload }
    case 'SET_SELECTED_PIPELINE':
      return { ...state, selectedPipeline: action.payload }
    case 'SET_TEMPLATE_RESULT':
      return {
        ...state,
        templateTitle: action.payload.template_title || '',
        placeholders: action.payload.placeholders || [],
        templateReady: true,
      }
    case 'UPDATE_PLACEHOLDERS':
      return { ...state, placeholders: action.payload }
    case 'CONFIRM_GATE': {
      const gates = [...state.gates]
      gates[action.payload] = true
      return { ...state, gates, pipelineStep: action.payload + 1 }
    }
    case 'UNCONFIRM_GATE': {
      const gates = [...state.gates]
      gates[action.payload] = false
      return { ...state, gates }
    }
    case 'SET_EXTRACTION_RESULTS':
      return { ...state, extractionResults: action.payload }
    case 'SET_CONFIRMED_VALUES':
      return { ...state, confirmedValues: action.payload }
    case 'SET_SPEC':
      return {
        ...state,
        spec: action.payload.spec,
        validation: action.payload.validation,
        specVersions: action.payload.version
          ? [...state.specVersions, action.payload.version]
          : state.specVersions,
      }
    case 'SET_DIAGRAM':
      return { ...state, diagramCode: action.payload }
    case 'SET_SPEC_VERSIONS':
      return { ...state, specVersions: action.payload }
    case 'SET_APPROVED_VERSION':
      return { ...state, approvedVersionId: action.payload }

    // Chat
    case 'TOGGLE_CHAT':
      return { ...state, chatOpen: !state.chatOpen }
    case 'ADD_CHAT_MESSAGE':
      return { ...state, chatHistory: [...state.chatHistory, action.payload] }

    default:
      return state
  }
}

export function ProjectProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState)

  const refreshProject = useCallback(async () => {
    if (!state.projectId) return
    try {
      const res = await getProject(state.projectId)
      dispatch({ type: 'SET_PROJECT', payload: res.data })
    } catch { /* ignore */ }
  }, [state.projectId])

  return (
    <ProjectContext.Provider value={{ state, dispatch, refreshProject, STEPS }}>
      {children}
    </ProjectContext.Provider>
  )
}

export function useProject() {
  const ctx = useContext(ProjectContext)
  if (!ctx) throw new Error('useProject must be within ProjectProvider')
  return ctx
}

export { STEPS }
