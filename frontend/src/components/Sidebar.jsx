import { FolderKanban, ArrowLeft } from 'lucide-react'
import { useProject } from '../context/ProjectContext'
import ThemeToggle from './ThemeToggle'

const JEMS_GRADIENT = 'linear-gradient(105deg, #2a1a4e 0%, #7b1fa2 25%, #e91e8c 55%, #ff6f00 85%, #ffab40 100%)'

const NAV_ITEMS = [
  { id: 'projects', label: 'Projects', icon: FolderKanban },
]

export default function Sidebar() {
  const { state, dispatch } = useProject()
  const { currentPage, project } = state

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        {/* Gradient J logo — matches LandingPage */}
        <div style={{
          width: 36, height: 36, borderRadius: 10,
          background: JEMS_GRADIENT,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: "'Syne', sans-serif", fontWeight: 800, fontSize: 18,
          color: '#fff', flexShrink: 0, userSelect: 'none',
          boxShadow: '0 0 20px rgba(233,30,140,0.3)',
        }}>J</div>
        <div className="brand-text">
          <h1 style={{ fontFamily: "'Syne', sans-serif", fontWeight: 800, letterSpacing: '-0.02em' }}>
            Jems
          </h1>
          <span className="brand-tag">Spec Generator</span>
        </div>
      </div>

      <div className="sidebar-divider" />

      <nav>
        {NAV_ITEMS.map(item => {
          const Icon = item.icon
          return (
            <button key={item.id}
              className={currentPage === item.id ? 'active' : ''}
              onClick={() => dispatch({ type: 'SET_PAGE', payload: item.id })}>
              <Icon size={16} />
              {item.label}
            </button>
          )
        })}
      </nav>

      {/* Active project indicator */}
      {project && currentPage === 'pipeline' && (
        <>
          <div className="sidebar-divider" />
          <div className="sidebar-project-indicator">
            <span className="spi-label">Active Project</span>
            <span className="spi-name">{project.name}</span>
            <button className="btn btn-secondary spi-back"
              onClick={() => dispatch({ type: 'CLOSE_PROJECT' })}>
              <ArrowLeft size={12} /> Back to Projects
            </button>
          </div>
        </>
      )}

      <div className="sidebar-footer">
        <div className="sidebar-divider" />
        <div className="sidebar-footer-row">
          <span className="sidebar-version">v2.4.1 · Live</span>
          <ThemeToggle />
        </div>
      </div>
    </aside>
  )
}
