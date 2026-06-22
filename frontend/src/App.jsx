import { useState, useEffect } from 'react'
import { ProjectProvider, useProject } from './context/ProjectContext'
import Sidebar from './components/Sidebar'
import ChatPanel from './components/ChatPanel'
import ProjectsPage from './pages/ProjectsPage'
import ConnectionsPage from './pages/ConnectionsPage'
import PipelinePage from './pages/PipelinePage'
import LandingPage from './pages/LandingPage'

function AppContent({ initialPage }) {
  const { state, dispatch } = useProject()
  const { currentPage } = state

  // Navigate to the page the user clicked from the landing screen
  useEffect(() => {
    if (initialPage && initialPage !== 'projects') {
      dispatch({ type: 'SET_PAGE', payload: initialPage })
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

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
  const [entered, setEntered] = useState(false)
  const [dark, setDark] = useState(true)
  const [initialPage, setInitialPage] = useState('projects')

  // Keep data-theme in sync with the dark toggle (works for landing AND platform)
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  // Restore persisted preference on first load
  useEffect(() => {
    const saved = localStorage.getItem('theme')
    if (saved === 'light') setDark(false)
  }, [])

  const handleEnter = (page = 'projects') => {
    setInitialPage(page)
    setEntered(true)
  }

  if (!entered) {
    return (
      <LandingPage
        onEnter={handleEnter}
        dark={dark}
        toggleTheme={() => setDark(d => !d)}
      />
    )
  }

  return (
    <ProjectProvider>
      <AppContent initialPage={initialPage} />
    </ProjectProvider>
  )
}

export default App
