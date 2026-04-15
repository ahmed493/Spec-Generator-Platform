import { useState, useEffect } from 'react'
import {
  Github, Database, Cloud, BarChart3, HardDrive,
  Check, Loader2, X, Eye, EyeOff, Unplug,
} from 'lucide-react'
import { getConnections, connectGitHub, connectPowerBI, connectPostgreSQL, disconnectSource } from '../api'

/* ============== Connection Modal ============== */
function ConnectModal({ source, onClose, onSuccess }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [showSecrets, setShowSecrets] = useState({})

  // GitHub fields
  const [ghToken, setGhToken] = useState('')

  // Power BI fields
  const [pbiTenantId, setPbiTenantId] = useState('')
  const [pbiClientId, setPbiClientId] = useState('')
  const [pbiClientSecret, setPbiClientSecret] = useState('')

  // PostgreSQL fields
  const [pgHost, setPgHost] = useState('')
  const [pgPort, setPgPort] = useState(5432)
  const [pgDatabase, setPgDatabase] = useState('')
  const [pgUser, setPgUser] = useState('')
  const [pgPassword, setPgPassword] = useState('')

  // BigQuery fields
  const [bqKeyFile, setBqKeyFile] = useState(null)
  const [bqKeyContent, setBqKeyContent] = useState('')

  // GCS fields
  const [gcsKeyFile, setGcsKeyFile] = useState(null)
  const [gcsKeyContent, setGcsKeyContent] = useState('')

  const toggleShow = (field) =>
    setShowSecrets((prev) => ({ ...prev, [field]: !prev[field] }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      if (source.id === 'github') {
        await connectGitHub(ghToken)
      } else if (source.id === 'powerbi') {
        await connectPowerBI(pbiTenantId, pbiClientId, pbiClientSecret)
      } else if (source.id === 'postgresql') {
        await connectPostgreSQL(pgHost, pgPort, pgDatabase, pgUser, pgPassword)
      } else if (source.id === 'bigquery') {
        await connectBigQuery(bqKeyContent)
      } else if (source.id === 'gcs') {
        await connectGCS(gcsKeyContent)
      }
      onSuccess()
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    }
    setLoading(false)
  }
        {/* BigQuery Modal */}
        {source.id === 'bigquery' && (
          <>
            <label>Service Account JSON</label>
            <input
              type="file"
              accept="application/json"
              onChange={async (e) => {
                const file = e.target.files[0]
                setBqKeyFile(file)
                if (file) {
                  const text = await file.text()
                  setBqKeyContent(text)
                }
              }}
              required
            />
            <p className="form-hint">
              Upload your Google Cloud service account JSON key. The file is read locally and never uploaded to any server except your own backend.
            </p>
          </>
        )}

        {/* GCS Modal */}
        {source.id === 'gcs' && (
          <>
            <label>Service Account JSON</label>
            <input
              type="file"
              accept="application/json"
              onChange={async (e) => {
                const file = e.target.files[0]
                setGcsKeyFile(file)
                if (file) {
                  const text = await file.text()
                  setGcsKeyContent(text)
                }
              }}
              required
            />
            <p className="form-hint">
              Upload your Google Cloud service account JSON key. The file is read locally and never uploaded to any server except your own backend.
            </p>
          </>
        )}

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-row">
            <source.icon size={20} />
            <h3>Connect to {source.name}</h3>
          </div>
          <button className="modal-close" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <p className="modal-desc">{source.connectHelp}</p>

        {error && <div className="message error">{error}</div>}

        <form onSubmit={handleSubmit}>
          {source.id === 'github' && (
            <>
              <label>Personal Access Token</label>
              <div className="input-group">
                <input
                  type={showSecrets.ghToken ? 'text' : 'password'}
                  placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                  value={ghToken}
                  onChange={(e) => setGhToken(e.target.value)}
                  required
                />
                <button type="button" className="input-toggle" onClick={() => toggleShow('ghToken')}>
                  {showSecrets.ghToken ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              <p className="form-hint">
                Create a token at GitHub → Settings → Developer settings → Personal access tokens. 
                Needs <code>repo</code> scope.
              </p>
            </>
          )}

          {source.id === 'powerbi' && (
            <>
              <label>Tenant ID (Directory ID)</label>
              <input
                type="text"
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                value={pbiTenantId}
                onChange={(e) => setPbiTenantId(e.target.value)}
                required
              />

              <label>Client ID (Application ID)</label>
              <input
                type="text"
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                value={pbiClientId}
                onChange={(e) => setPbiClientId(e.target.value)}
                required
              />

              <label>Client Secret</label>
              <div className="input-group">
                <input
                  type={showSecrets.pbiSecret ? 'text' : 'password'}
                  placeholder="Your client secret value"
                  value={pbiClientSecret}
                  onChange={(e) => setPbiClientSecret(e.target.value)}
                  required
                />
                <button type="button" className="input-toggle" onClick={() => toggleShow('pbiSecret')}>
                  {showSecrets.pbiSecret ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              <p className="form-hint">
                Register an App in Azure AD → App registrations. Add Power BI Service permissions 
                and grant admin consent. The service principal must be added to the Power BI workspace.
              </p>
            </>
          )}

          {source.id === 'postgresql' && (
            <>
              <label>Host</label>
              <input
                type="text"
                placeholder="localhost"
                value={pgHost}
                onChange={(e) => setPgHost(e.target.value)}
                required
              />

              <label>Port</label>
              <input
                type="number"
                placeholder="5432"
                value={pgPort}
                onChange={(e) => setPgPort(parseInt(e.target.value))}
                required
              />

              <label>Database</label>
              <input
                type="text"
                placeholder="postgres"
                value={pgDatabase}
                onChange={(e) => setPgDatabase(e.target.value)}
                required
              />

              <label>User</label>
              <input
                type="text"
                placeholder="postgres"
                value={pgUser}
                onChange={(e) => setPgUser(e.target.value)}
                required
              />

              <label>Password</label>
              <div className="input-group">
                <input
                  type={showSecrets.pgPassword ? 'text' : 'password'}
                  placeholder="Your database password"
                  value={pgPassword}
                  onChange={(e) => setPgPassword(e.target.value)}
                  required
                />
                <button type="button" className="input-toggle" onClick={() => toggleShow('pgPassword')}>
                  {showSecrets.pgPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              <p className="form-hint">
                Ensure the PostgreSQL server is accessible from this environment. 
                Default port is 5432. User must have sufficient permissions to query metadata.
              </p>
            </>
          )}

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn btn-filled" disabled={loading}>
              {loading ? (
                <>
                  <Loader2 size={14} className="spinner" />
                  Connecting...
                </>
              ) : (
                'Connect'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

/* ============== Main Page ============== */
function ConnectionsPage() {
  const [connections, setConnections] = useState({})
  const [message, setMessage] = useState(null)
  const [connectingSource, setConnectingSource] = useState(null) // which modal is open
  const [disconnecting, setDisconnecting] = useState(null)

  useEffect(() => {
    fetchConnections()
  }, [])

  const fetchConnections = async () => {
    try {
      const res = await getConnections()
      setConnections(res.data)
    } catch (err) {
      console.error('Error fetching connections:', err)
    }
  }

  const handleDisconnect = async (sourceId) => {
    setDisconnecting(sourceId)
    try {
      await disconnectSource(sourceId)
      setMessage({ type: 'success', text: `Disconnected from ${sourceId}` })
      fetchConnections()
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.detail || err.message })
    }
    setDisconnecting(null)
  }

  const connectedCount = Object.values(connections).filter(Boolean).length

  const sources = [
    {
      id: 'github',
      name: 'GitHub',
      icon: Github,
      description: 'Connect repositories to analyze source code and extract metadata',
      connectHelp: 'Enter your GitHub Personal Access Token to connect. Your token is sent securely and never stored on disk.',
      available: true,
    },
    {
      id: 'bigquery',
      name: 'BigQuery',
      icon: Database,
      description: 'Connect BigQuery to extract table schemas and data lineage',
      connectHelp: 'Upload your Google Cloud service account JSON key.',
      available: true,
    },
    {
      id: 'postgresql',
      name: 'PostgreSQL',
      icon: HardDrive,
      description: 'Connect PostgreSQL databases to analyze schemas and relationships',
      connectHelp: 'Enter your PostgreSQL connection details.',
      available: true,
    },
    {
      id: 'powerbi',
      name: 'Power BI',
      icon: BarChart3,
      description: 'Connect Power BI to analyze reports, datasets and DAX measures',
      connectHelp: 'Provide your Azure AD Service Principal credentials. The app registration needs Power BI API permissions.',
      available: true,
    },
    {
      id: 'gcs',
      name: 'Google Cloud Storage',
      icon: Cloud,
      description: 'Connect GCS to explore data files and storage structure',
      connectHelp: 'Upload your Google Cloud service account JSON key.',
      available: true,
    },
  ]

  return (
    <div>
      <div className="page-header">
        <h2>Connections</h2>
        <p>Connect your data sources to start generating specifications.</p>
      </div>

      {/* Stats */}
      <div className="stats-bar">
        <div className="stat-card">
          <div className="stat-label">Connected Sources</div>
          <div className="stat-value">{connectedCount}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Available Sources</div>
          <div className="stat-value">{sources.filter((s) => s.available).length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Sources</div>
          <div className="stat-value">{sources.length}</div>
        </div>
      </div>

      {message && (
        <div className={`message ${message.type}`}>{message.text}</div>
      )}

      <div className="connections-grid">
        {sources.map((source) => {
          const Icon = source.icon
          const isConnected = connections[source.id]

          return (
            <div key={source.id} className={`connection-card ${isConnected ? 'card-connected' : ''}`}>
              <div className="card-header">
                <div className={`card-icon ${isConnected ? 'icon-active' : ''}`}>
                  <Icon size={18} />
                </div>
                <h3>{source.name}</h3>
              </div>

              <p className="card-desc">{source.description}</p>

              <div className={`card-status ${isConnected ? 'connected' : 'disconnected'}`}>
                <span className="dot" />
                {isConnected ? 'Connected' : 'Not connected'}
              </div>

              {/* Connect button */}
              {source.available && !isConnected && (
                <button
                  className="btn btn-filled"
                  onClick={() => setConnectingSource(source)}
                >
                  Connect
                </button>
              )}

              {/* Connected — show disconnect */}
              {isConnected && (
                <div className="card-actions">
                  <button className="btn btn-success" disabled>
                    <Check size={14} />
                    Connected
                  </button>
                  <button
                    className="btn btn-danger-outline"
                    onClick={() => handleDisconnect(source.id)}
                    disabled={disconnecting === source.id}
                  >
                    {disconnecting === source.id ? (
                      <Loader2 size={14} className="spinner" />
                    ) : (
                      <Unplug size={14} />
                    )}
                    Disconnect
                  </button>
                </div>
              )}

              {/* Coming soon */}
              {!source.available && (
                <button className="btn btn-primary" disabled>
                  Coming soon
                </button>
              )}
            </div>
          )
        })}
      </div>

      {/* Connection Modal */}
      {connectingSource && (
        <ConnectModal
          source={connectingSource}
          onClose={() => setConnectingSource(null)}
          onSuccess={() => {
            setConnectingSource(null)
            setMessage({ type: 'success', text: `${connectingSource.name} connected successfully!` })
            fetchConnections()
          }}
        />
      )}
    </div>
  )
}

export default ConnectionsPage
