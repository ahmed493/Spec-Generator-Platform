import { createContext, useContext, useReducer, useCallback } from 'react'
import { getProject } from '../api'

const ProjectContext = createContext(null)

const STEPS = ['template', 'extraction', 'mapping', 'export']

const initialState = {
  // Navigation
  currentPage: 'projects',    // projects | connections | pipeline
  // Active project
  project: null,
  projectId: null,
  // Pipeline
  pipelineStep: 0,            // 0-3 index into STEPS
  gates: [false, false, false], // confirmed flags for gates 1-3
  templateTitle: '',
  placeholders: [],
  extractionResults: [],
  confirmedValues: {},
  spec: '',
  validation: null,
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
        gates: [false, false, false],
        templateTitle: '',
        placeholders: [],
        extractionResults: [],
        confirmedValues: {},
        spec: '',
        validation: null,
        chatHistory: [],
      }
    case 'SET_PROJECT':
      return { ...state, project: action.payload }
    case 'CLOSE_PROJECT':
      return { ...initialState, currentPage: 'projects' }

    // Pipeline
    case 'SET_PIPELINE_STEP':
      return { ...state, pipelineStep: action.payload }
    case 'SET_TEMPLATE_RESULT':
      return {
        ...state,
        templateTitle: action.payload.template_title || '',
        placeholders: action.payload.placeholders || [],
        pipelineStep: 0,
      }
    case 'UPDATE_PLACEHOLDERS':
      return { ...state, placeholders: action.payload }
    case 'CONFIRM_GATE': {
      const gates = [...state.gates]
      gates[action.payload] = true
      return { ...state, gates, pipelineStep: action.payload + 1 }
    }
    case 'SET_EXTRACTION_RESULTS':
      return { ...state, extractionResults: action.payload }
    case 'SET_CONFIRMED_VALUES':
      return { ...state, confirmedValues: action.payload }
    case 'SET_SPEC':
      return { ...state, spec: action.payload.spec, validation: action.payload.validation }

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
