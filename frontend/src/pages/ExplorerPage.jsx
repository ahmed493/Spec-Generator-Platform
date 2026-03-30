import { useState, useEffect } from 'react'
import { GitBranch, Folder, File, Code2, Database, FolderOpen, AlertCircle } from 'lucide-react'
import { getRepoStructure, getRepoMetadata, getGitHubRepos } from '../api'

function ExplorerPage() {
  const [repos, setRepos] = useState([])
  const [owner, setOwner] = useState('')
  const [selectedRepo, setSelectedRepo] = useState(null)
  const [structure, setStructure] = useState(null)
  const [metadata, setMetadata] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingRepos, setLoadingRepos] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchRepos()
  }, [])

  const fetchRepos = async () => {
    setLoadingRepos(true)
    setError(null)
    try {
      const res = await getGitHubRepos()
      setRepos(res.data.repos || [])
      setOwner(res.data.owner || '')
    } catch (err) {
      setError('Connect to GitHub first to see your repositories.')
      setRepos([])
    }
    setLoadingRepos(false)
  }

  const handleSelectRepo = async (repo) => {
    setSelectedRepo(repo.name)
    setLoading(true)
    setError(null)
    setStructure(null)
    setMetadata(null)

    try {
      const [structRes, metaRes] = await Promise.all([
        getRepoStructure(repo.owner, repo.name),
        getRepoMetadata(repo.owner, repo.name),
      ])
      setStructure(structRes.data)
      setMetadata(metaRes.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Error loading repository data')
    }
    setLoading(false)
  }

  return (
    <div>
      <div className="page-header">
        <h2>Explorer</h2>
        <p>Select a repository to explore its structure and metadata.</p>
      </div>

      {error && <div className="message error"><AlertCircle size={14} />{error}</div>}

      {loadingRepos && (
        <div className="loading">
          <div className="spinner"></div>
          <span>Loading repositories...</span>
        </div>
      )}

      {!loadingRepos && repos.length === 0 && !error && (
        <div className="message">No repositories found. Connect to GitHub first.</div>
      )}

      <div className="repo-list">
        {repos.map((repo) => (
          <div
            key={repo.name}
            className={`repo-card ${selectedRepo === repo.name ? 'selected' : ''}`}
            onClick={() => handleSelectRepo(repo)}
          >
            <h4>
              <GitBranch size={14} />
              {repo.name}
            </h4>
            <p>{repo.description || repo.language || 'No description'}</p>
          </div>
        ))}
      </div>

      {loading && (
        <div className="loading">
          <div className="spinner"></div>
          <span>Extracting metadata...</span>
        </div>
      )}

      {metadata && (
        <div className="section">
          <h3 className="section-title">
            <FolderOpen size={16} />
            {selectedRepo}
          </h3>

          {/* Languages */}
          <div className="file-tree">
            <h4>
              <Code2 size={14} />
              Languages
            </h4>
            <div className="lang-tags">
              {Object.entries(metadata.languages || {}).map(([lang, bytes]) => (
                <span key={lang} className="lang-tag">
                  {lang}: {(bytes / 1024).toFixed(1)} KB
                </span>
              ))}
            </div>
          </div>

          {/* Structure */}
          {structure && (
            <div className="file-tree">
              <h4>
                <Folder size={14} />
                Structure
              </h4>
              {(structure.files || []).map((file) => (
                <div key={file.path} className={`file-item ${file.type === 'dir' ? 'dir' : ''}`}>
                  {file.type === 'dir' ? <Folder size={14} /> : <File size={14} />}
                  {file.path}
                </div>
              ))}
            </div>
          )}

          {/* SQL Files */}
          {metadata.sql_files && metadata.sql_files.length > 0 && (
            <div className="file-tree">
              <h4>
                <Database size={14} />
                SQL Files ({metadata.sql_files.length})
              </h4>
              {metadata.sql_files.map((file) => (
                <details key={file.path}>
                  <summary>{file.path}</summary>
                  <pre className="code-block">{file.content}</pre>
                </details>
              ))}
            </div>
          )}

          {/* Python Files */}
          {metadata.python_files && metadata.python_files.length > 0 && (
            <div className="file-tree">
              <h4>
                <Code2 size={14} />
                Python Files ({metadata.python_files.length})
              </h4>
              {metadata.python_files.map((file) => (
                <details key={file.path}>
                  <summary>{file.path}</summary>
                  <pre className="code-block">{file.content}</pre>
                </details>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default ExplorerPage
