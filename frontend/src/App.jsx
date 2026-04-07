import { ProjectProvider, useProject } from './context/ProjectContext'
import Sidebar from './components/Sidebar'
import ChatPanel from './components/ChatPanel'
import ProjectsPage from './pages/ProjectsPage'
import ConnectionsPage from './pages/ConnectionsPage'
import PipelinePage from './pages/PipelinePage'

function AppContent() {
  const { state } = useProject()
  const { currentPage } = state

  const renderPage = () => {
    switch (currentPage) {
      case 'projects':
        return <ProjectsPage />
      case 'connections':
        return <ConnectionsPage />
      case 'pipeline':
        return <PipelinePage />
      default:
        return <ProjectsPage />
    }
  }

  return (
    <div className="app">
      <Sidebar />
      <main className="main-content" key={currentPage}>
        {renderPage()}
      </main>
      <ChatPanel />
    </div>
  )
}

function App() {
  return (
    <ProjectProvider>
      <AppContent />
    </ProjectProvider>
  )
}

export default App
