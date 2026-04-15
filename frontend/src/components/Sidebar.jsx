import { FolderKanban, Link2, ArrowLeft } from 'lucide-react'
import { useProject } from '../context/ProjectContext'
import ThemeToggle from './ThemeToggle'
import logoSvg from '../assets/logo.svg'

const NAV_ITEMS = [
  { id: 'projects', label: 'Projects', icon: FolderKanban },
  { id: 'connections', label: 'Connections', icon: Link2 },
]

export default function Sidebar() {
  const { state, dispatch } = useProject()
  const { currentPage, project } = state

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-logo-wrap">
          <img src={logoSvg} alt="Logo" className="brand-logo-img" />
        </div>
        <div className="brand-text">
          <h1>Spec Generator</h1>
          <span className="brand-tag">AI-Powered</span>
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
          <span className="sidebar-version">v1.0 — Built with precision</span>
          <ThemeToggle />
        </div>
      </div>
    </aside>
  )
}
