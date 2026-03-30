import { useState } from 'react'
import { Link2, FolderSearch, FileText, Zap } from 'lucide-react'
import ConnectionsPage from './pages/ConnectionsPage'
import ExplorerPage from './pages/ExplorerPage'
import SpecPage from './pages/SpecPage'

import ChatbotPanel from './pages/ChatbotPanel'

const pages = [
  { id: 'connections', label: 'Connections', icon: Link2 },
  { id: 'explorer', label: 'Explorer', icon: FolderSearch },
  { id: 'spec', label: 'Generate Spec', icon: FileText },
  { id: 'chat', label: 'Chatbot', icon: Zap },
]

function App() {
  const [currentPage, setCurrentPage] = useState('connections')

  const renderPage = () => {
    switch (currentPage) {
      case 'connections':
        return <ConnectionsPage />
      case 'explorer':
        return <ExplorerPage />
      case 'spec':
        return <SpecPage />
      case 'chat':
        return <ChatbotPanel />
      default:
        return <ConnectionsPage />
    }
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon">
            <Zap size={16} />
          </div>
          <h1>Spec Generator</h1>
        </div>
        <div className="sidebar-divider" />
        <nav>
          {pages.map((page) => {
            const Icon = page.icon
            return (
              <button
                key={page.id}
                className={currentPage === page.id ? 'active' : ''}
                onClick={() => setCurrentPage(page.id)}
              >
                <Icon size={16} />
                {page.label}
              </button>
            )
          })}
        </nav>
      </aside>
      <main className="main-content">
        {renderPage()}
      </main>
    </div>
  )
}

export default App
