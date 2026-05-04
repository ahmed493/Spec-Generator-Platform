import axios from 'axios'

const API_BASE = '/api'

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Health
export const healthCheck = () => api.get('/health')

// Connections
export const getConnections = () => api.get('/connections')
export const connectGitHub = (token) =>
  api.post('/connect/github', { token })
export const connectPowerBI = (tenant_id, client_id, client_secret) =>
  api.post('/connect/powerbi', { tenant_id, client_id, client_secret })
export const disconnectSource = (source) =>
  api.post('/disconnect', { source })

// GitHub
export const getGitHubUser = () => api.get('/github/user')
export const getGitHubRepos = () => api.get('/github/repos')

export const getRepoStructure = (owner, repoName) =>
  api.post('/github/repo-structure', { owner, repo_name: repoName })

export const getRepoMetadata = (owner, repoName) =>
  api.post('/github/repo-metadata', { owner, repo_name: repoName })

// Power BI
export const getPowerBIWorkspaces = () => api.get('/powerbi/workspaces')
export const getPowerBIDatasets = (workspaceId) =>
  api.post('/powerbi/datasets', { workspace_id: workspaceId })
export const getPowerBIReports = (workspaceId) =>
  api.post('/powerbi/reports', { workspace_id: workspaceId })
export const getPowerBIDatasetTables = (workspaceId, datasetId) =>
  api.post('/powerbi/dataset-tables', { workspace_id: workspaceId, dataset_id: datasetId })
export const getPowerBIDataflows = (workspaceId) =>
  api.post('/powerbi/dataflows', { workspace_id: workspaceId })
export const getPowerBIWorkspaceMetadata = (workspaceId) =>
  api.post('/powerbi/workspace-metadata', { workspace_id: workspaceId })

// Spec Generation
export const generateSpec = (owner, repoName) =>
  api.post('/generate-spec', { owner, repo_name: repoName })

export const generateSpecFromTemplate = (repoList, templateFile, pipeline = null) => {
  // repoList: [{owner, repo_name}, ...]
  const formData = new FormData()
  formData.append('repos', JSON.stringify(repoList))
  formData.append('template_file', templateFile)
  if (pipeline) {
    formData.append('pipeline', JSON.stringify(pipeline))
  }
  return axios.post(`${API_BASE}/generate-spec-from-template`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const detectPipelines = (repoList) => {
  // repoList: [{owner, repo_name}, ...]
  const formData = new FormData()
  formData.append('repos', JSON.stringify(repoList))
  return axios.post(`${API_BASE}/detect-pipelines`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// Chat
export const chat = (question, repoName = null) =>
  api.post('/chat', { question, repo_name: repoName })

// ================= PROJECTS =================
export const getProjects = () => api.get('/projects')
export const createProject = (name, description = '') =>
  api.post('/projects', { name, description })
export const getProject = (projectId) => api.get(`/projects/${projectId}`)
export const updateProject = (projectId, data) =>
  api.put(`/projects/${projectId}`, data)
export const deleteProject = (projectId) =>
  api.delete(`/projects/${projectId}`)

// Project Sources
export const addProjectSource = (projectId, type, label = '', config = {}) =>
  api.post(`/projects/${projectId}/sources`, { type, label, config })
export const removeProjectSource = (projectId, sourceId) =>
  api.delete(`/projects/${projectId}/sources/${sourceId}`)
export const getSourceTypes = () => api.get('/source-types')
export const getProjectApprovedSpecs = (projectId) =>
  api.get(`/projects/${projectId}/approved-specs`)

// ================= PIPELINE (step-by-step) =================
export const pipelineDetectPipelines = (projectId) =>
  api.post(`/projects/${projectId}/pipeline/detect-pipelines`, null, { timeout: 600000 })
export const pipelineSelect = (projectId, pipelineId) =>
  api.post(`/projects/${projectId}/pipeline/select`, { pipeline_id: pipelineId })
export const pipelineUpdatePipelines = (projectId, pipelines) =>
  api.post(`/projects/${projectId}/pipeline/update-pipelines`, { pipelines })
export const pipelineSplit = (projectId, pipelineId, splitName1, splitName2) =>
  api.post(`/projects/${projectId}/pipeline/split`, {
    pipeline_id: pipelineId,
    split_name_1: splitName1,
    split_name_2: splitName2,
  })
export const pipelineMerge = (projectId, pipelineIds, mergedName) =>
  api.post(`/projects/${projectId}/pipeline/merge`, {
    pipeline_ids: pipelineIds,
    merged_name: mergedName,
  })
export const pipelineReorder = (projectId, pipelineIds) =>
  api.post(`/projects/${projectId}/pipeline/reorder`, { pipeline_ids: pipelineIds })
export const pipelineResetPipelines = (projectId) =>
  api.post(`/projects/${projectId}/pipeline/reset-pipelines`)
export const pipelineSaveCatalog = (projectId) =>
  api.post(`/projects/${projectId}/pipeline/save-catalog`)
export const pipelineGetCatalog = (projectId) =>
  api.get(`/projects/${projectId}/pipeline/catalog`)
export const pipelineTemplate = (projectId, templateFile) => {
  const formData = new FormData()
  formData.append('template_file', templateFile)
  return axios.post(`${API_BASE}/projects/${projectId}/pipeline/template`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
export const pipelineExtract = (projectId, placeholders) =>
  api.post(`/projects/${projectId}/pipeline/extract`, { placeholders })
export const pipelineMap = (projectId, values) =>
  api.post(`/projects/${projectId}/pipeline/map`, { values })
export const pipelineExport = (projectId, format = 'markdown') =>
  api.post(`/projects/${projectId}/pipeline/export`, { format })
export const pipelineGetState = (projectId) =>
  api.get(`/projects/${projectId}/pipeline/state`)
export const pipelineGetSpecVersions = (projectId) =>
  api.get(`/projects/${projectId}/pipeline/spec-versions`)
export const pipelineDiffSpecVersions = (projectId, fromVersionId, toVersionId) =>
  api.post(`/projects/${projectId}/pipeline/spec-versions/diff`, {
    from_version_id: fromVersionId,
    to_version_id: toVersionId,
  })
export const pipelinePromoteSpecVersion = (projectId, versionId) =>
  api.post(`/projects/${projectId}/pipeline/spec-versions/${versionId}/promote`)

// ================= PROJECT CHAT =================
export const projectChat = (projectId, question, pipelineStep = '', placeholders = [], extractedValues = {}) =>
  api.post(`/projects/${projectId}/chat`, {
    question,
    pipeline_step: pipelineStep,
    placeholders,
    extracted_values: extractedValues,
  })

// ================= POSTGRESQL =================
export const connectPostgreSQL = (host, port, database, user, password) =>
  api.post('/connect/postgresql', { host, port, database, user, password })

export const getPostgreSQLSchemas = () => api.get('/postgresql/schemas')
export const getPostgreSQLTables = (schema = 'public') =>
  api.post('/postgresql/tables', { schema })
export const getPostgreSQLColumns = (schema = 'public') =>
  api.post('/postgresql/columns', { schema })
export const getPostgreSQLForeignKeys = (schema = 'public') =>
  api.post('/postgresql/foreign-keys', { schema })
export const getPostgreSQLSchemaMetadata = (schema = 'public') =>
  api.post('/postgresql/schema-metadata', { schema })

// ================= BIGQUERY =================
export const connectBigQuery = (service_account_json) =>
  api.post('/connect/bigquery', { service_account_json })

export const getBigQueryDatasets = () => api.get('/bigquery/datasets')
export const getBigQueryTables = (dataset_id) =>
  api.post('/bigquery/tables', { dataset_id })
export const getBigQueryTableSchema = (dataset_id, table_id) =>
  api.post('/bigquery/table-schema', { dataset_id, table_id })
export const previewBigQueryTable = (dataset_id, table_id) =>
  api.post('/bigquery/preview', { dataset_id, table_id })
export const getBigQueryDatasetMetadata = (dataset_id) =>
  api.post('/bigquery/dataset-metadata', { dataset_id })

// ================= GCS =================
export const connectGCS = (service_account_json) =>
  api.post('/connect/gcs', { service_account_json })

export const getGCSBuckets = () => api.get('/gcs/buckets')
export const getGCSBlobs = (bucket_name, prefix = '') =>
  api.post('/gcs/blobs', { bucket_name, prefix })
export const getGCSCSVHeader = (bucket_name, blob_name) =>
  api.post('/gcs/csv-header', { bucket_name, blob_name })
export const getGCSJSONStructure = (bucket_name, blob_name) =>
  api.post('/gcs/json-structure', { bucket_name, blob_name })
export const getGCSBucketMetadata = (bucket_name, prefix = '') =>
  api.post('/gcs/bucket-metadata', { bucket_name, prefix })

export default api
