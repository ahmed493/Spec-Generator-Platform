"""
API Routes for Spec Generator
All connections are initiated from the frontend (no hardcoded tokens).
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from app.mcp_servers.github_server import GitHubMCPServer
from app.mcp_servers.powerbi_server import PowerBIMCPServer
from app.mcp_servers.bigquery_server import BigQueryMCPServer
from app.mcp_servers.postgresql_server import PostgreSQLMCPServer
from app.mcp_servers.gcs_server import GCSMCPServer
from app.agents.spec_agent import SpecAgent
from app.config.settings import settings
"""from app.auth_sso import get_current_user, require_role"""
import json

router = APIRouter()

# Store connections in memory (in production, use a database)
connections = {
    "github": None,
    "bigquery": None,
    "postgresql": None,
    "powerbi": None,
    "gcs": None,
}
specs_cache = {}


# ============== REQUEST / RESPONSE MODELS ==============

class GitHubConnectRequest(BaseModel):
    token: str  # Always required — provided from the UI


class PowerBIConnectRequest(BaseModel):
    tenant_id: str
    client_id: str
    client_secret: str


class BigQueryConnectRequest(BaseModel):
    service_account_json: str  # JSON string of the service account key


class PostgreSQLConnectRequest(BaseModel):
    host: str
    port: int = 5432
    database: str
    user: str
    password: str


class GCSConnectRequest(BaseModel):
    service_account_json: str  # JSON string of the service account key


class BigQueryDatasetRequest(BaseModel):
    dataset_id: str


class BigQueryTableRequest(BaseModel):
    dataset_id: str
    table_id: str


class GCSBucketRequest(BaseModel):
    bucket_name: str
    prefix: str = ""


class GCSBlobRequest(BaseModel):
    bucket_name: str
    blob_name: str


class PostgreSQLSchemaRequest(BaseModel):
    schema: str = "public"


class RepoRequest(BaseModel):
    owner: str
    repo_name: str


class WorkspaceRequest(BaseModel):
    workspace_id: str


class DatasetRequest(BaseModel):
    workspace_id: str
    dataset_id: str


class ReportPagesRequest(BaseModel):
    workspace_id: str
    report_id: str


class ChatRequest(BaseModel):
    question: str
    repo_name: Optional[str] = None


class DisconnectRequest(BaseModel):
    source: str


class ConnectionStatus(BaseModel):
    source: str
    connected: bool
    message: str


# ============== CONNECTION ENDPOINTS ==============

@router.post("/connect/github", response_model=ConnectionStatus)
async def connect_github(request: GitHubConnectRequest):
    """Connect to GitHub using a personal access token provided from the UI"""
    if not request.token or not request.token.strip():
        raise HTTPException(status_code=400, detail="GitHub token is required")

    server = GitHubMCPServer(request.token.strip())
    success = server.connect()

    if success:
        connections["github"] = server
        return ConnectionStatus(source="github", connected=True, message="Successfully connected to GitHub")
    else:
        raise HTTPException(status_code=401, detail="Invalid GitHub token")


@router.post("/connect/powerbi", response_model=ConnectionStatus)
async def connect_powerbi(request: PowerBIConnectRequest):
    """Connect to Power BI using Azure AD Service Principal credentials from the UI"""
    if not all([request.tenant_id.strip(), request.client_id.strip(), request.client_secret.strip()]):
        raise HTTPException(status_code=400, detail="All Power BI fields are required (tenant_id, client_id, client_secret)")

    server = PowerBIMCPServer(
        tenant_id=request.tenant_id.strip(),
        client_id=request.client_id.strip(),
        client_secret=request.client_secret.strip(),
    )
    success = server.connect()

    if success:
        connections["powerbi"] = server
        return ConnectionStatus(source="powerbi", connected=True, message="Successfully connected to Power BI")
    else:
        raise HTTPException(status_code=401, detail="Failed to authenticate with Power BI. Check your tenant/client/secret.")


@router.post("/connect/bigquery", response_model=ConnectionStatus)
async def connect_bigquery(request: BigQueryConnectRequest):
    """Connect to BigQuery using a service account JSON key from the UI"""
    try:
        sa_json = json.loads(request.service_account_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for service account key")

    server = BigQueryMCPServer(sa_json)
    success = server.connect()
    if success:
        connections["bigquery"] = server
        return ConnectionStatus(source="bigquery", connected=True, message=f"Connected to BigQuery (project: {server.project_id})")
    else:
        raise HTTPException(status_code=401, detail="Failed to connect to BigQuery. Check your service account key.")


@router.post("/connect/postgresql", response_model=ConnectionStatus)
async def connect_postgresql(request: PostgreSQLConnectRequest):
    """Connect to PostgreSQL using host/port/user/password/database from the UI"""
    server = PostgreSQLMCPServer(
        host=request.host.strip(),
        port=request.port,
        database=request.database.strip(),
        user=request.user.strip(),
        password=request.password,
    )
    success = server.connect()
    if success:
        connections["postgresql"] = server
        return ConnectionStatus(source="postgresql", connected=True, message=f"Connected to PostgreSQL ({request.host}:{request.port}/{request.database})")
    else:
        raise HTTPException(status_code=401, detail="Failed to connect to PostgreSQL. Check your credentials.")


@router.post("/connect/gcs", response_model=ConnectionStatus)
async def connect_gcs(request: GCSConnectRequest):
    """Connect to GCS using a service account JSON key from the UI"""
    try:
        sa_json = json.loads(request.service_account_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for service account key")

    server = GCSMCPServer(sa_json)
    success = server.connect()
    if success:
        connections["gcs"] = server
        return ConnectionStatus(source="gcs", connected=True, message=f"Connected to GCS (project: {server.project_id})")
    else:
        raise HTTPException(status_code=401, detail="Failed to connect to GCS. Check your service account key.")


@router.post("/disconnect", response_model=ConnectionStatus)
async def disconnect(request: DisconnectRequest):
    """Disconnect a data source"""
    src = request.source.lower()
    if src not in connections:
        raise HTTPException(status_code=400, detail=f"Unknown source: {src}")
    connections[src] = None
    return ConnectionStatus(source=src, connected=False, message=f"Disconnected from {src}")


@router.get("/connections")
async def get_connections():
    """Get status of all connections"""
    return {
        "github": connections["github"] is not None,
        "bigquery": connections["bigquery"] is not None,
        "postgresql": connections["postgresql"] is not None,
        "powerbi": connections["powerbi"] is not None,
        "gcs": connections["gcs"] is not None,
    }


# ============== GITHUB ENDPOINTS ==============

@router.get("/github/user")
async def get_github_user():
    """Get the authenticated GitHub user info"""
    if not connections["github"]:
        raise HTTPException(status_code=400, detail="Not connected to GitHub")
    try:
        user = connections["github"].client.get_user()
        return {"login": user.login, "name": user.name, "avatar_url": user.avatar_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/github/repos")
async def list_github_repos():
    """List all repositories for the authenticated GitHub user"""
    if not connections["github"]:
        raise HTTPException(status_code=400, detail="Not connected to GitHub")
    try:
        user = connections["github"].client.get_user()
        repos = []
        for repo in user.get_repos(sort="updated"):
            repos.append({
                "name": repo.name,
                "description": repo.description or "",
                "language": repo.language,
                "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                "owner": repo.owner.login,
            })
        return {"repos": repos, "owner": user.login}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/github/repo-structure")
async def get_repo_structure(request: RepoRequest):
    """Get the structure of a GitHub repository"""
    if not connections["github"]:
        raise HTTPException(status_code=400, detail="Not connected to GitHub. Connect first via the Connections page.")
    structure = connections["github"].get_repo_structure(request.owner, request.repo_name)
    return structure


@router.post("/github/repo-metadata")
async def get_repo_metadata(request: RepoRequest):
    """Get comprehensive metadata from a GitHub repository"""
    if not connections["github"]:
        raise HTTPException(status_code=400, detail="Not connected to GitHub. Connect first via the Connections page.")
    metadata = connections["github"].get_repo_metadata(request.owner, request.repo_name)
    return metadata


# ============== POWER BI ENDPOINTS ==============

@router.get("/powerbi/workspaces")
async def get_powerbi_workspaces():
    """List all Power BI workspaces"""
    if not connections["powerbi"]:
        raise HTTPException(status_code=400, detail="Not connected to Power BI. Connect first via the Connections page.")
    return connections["powerbi"].get_workspaces()


@router.post("/powerbi/datasets")
async def get_powerbi_datasets(request: WorkspaceRequest):
    """List datasets in a Power BI workspace"""
    if not connections["powerbi"]:
        raise HTTPException(status_code=400, detail="Not connected to Power BI")
    return connections["powerbi"].get_datasets(request.workspace_id)


@router.post("/powerbi/reports")
async def get_powerbi_reports(request: WorkspaceRequest):
    """List reports in a Power BI workspace"""
    if not connections["powerbi"]:
        raise HTTPException(status_code=400, detail="Not connected to Power BI")
    return connections["powerbi"].get_reports(request.workspace_id)


@router.post("/powerbi/dataset-tables")
async def get_powerbi_dataset_tables(request: DatasetRequest):
    """Get tables and columns for a dataset"""
    if not connections["powerbi"]:
        raise HTTPException(status_code=400, detail="Not connected to Power BI")
    return connections["powerbi"].get_dataset_tables(request.workspace_id, request.dataset_id)


@router.post("/powerbi/dataset-datasources")
async def get_powerbi_dataset_datasources(request: DatasetRequest):
    """Get data sources connected to a dataset"""
    if not connections["powerbi"]:
        raise HTTPException(status_code=400, detail="Not connected to Power BI")
    return connections["powerbi"].get_dataset_datasources(request.workspace_id, request.dataset_id)


@router.post("/powerbi/report-pages")
async def get_powerbi_report_pages(request: ReportPagesRequest):
    """Get pages of a report"""
    if not connections["powerbi"]:
        raise HTTPException(status_code=400, detail="Not connected to Power BI")
    return connections["powerbi"].get_report_pages(request.workspace_id, request.report_id)


@router.post("/powerbi/dataflows")
async def get_powerbi_dataflows(request: WorkspaceRequest):
    """List dataflows in a Power BI workspace"""
    if not connections["powerbi"]:
        raise HTTPException(status_code=400, detail="Not connected to Power BI")
    return connections["powerbi"].get_dataflows(request.workspace_id)


@router.post("/powerbi/workspace-metadata")
async def get_powerbi_workspace_metadata(request: WorkspaceRequest):
    """Get full metadata for a Power BI workspace (datasets + reports + dataflows)"""
    if not connections["powerbi"]:
        raise HTTPException(status_code=400, detail="Not connected to Power BI")
    return connections["powerbi"].get_workspace_metadata(request.workspace_id)


# ============== BIGQUERY ENDPOINTS ==============

@router.get("/bigquery/datasets")
async def get_bq_datasets():
    """List all BigQuery datasets"""
    if not connections["bigquery"]:
        raise HTTPException(status_code=400, detail="Not connected to BigQuery")
    return connections["bigquery"].get_datasets()


@router.post("/bigquery/tables")
async def get_bq_tables(request: BigQueryDatasetRequest):
    """List tables in a BigQuery dataset"""
    if not connections["bigquery"]:
        raise HTTPException(status_code=400, detail="Not connected to BigQuery")
    return connections["bigquery"].get_tables(request.dataset_id)


@router.post("/bigquery/table-schema")
async def get_bq_table_schema(request: BigQueryTableRequest):
    """Get schema for a BigQuery table"""
    if not connections["bigquery"]:
        raise HTTPException(status_code=400, detail="Not connected to BigQuery")
    return connections["bigquery"].get_table_schema(request.dataset_id, request.table_id)


@router.post("/bigquery/preview")
async def preview_bq_table(request: BigQueryTableRequest):
    """Preview rows from a BigQuery table"""
    if not connections["bigquery"]:
        raise HTTPException(status_code=400, detail="Not connected to BigQuery")
    return connections["bigquery"].preview_rows(request.dataset_id, request.table_id)


@router.post("/bigquery/dataset-metadata")
async def get_bq_dataset_metadata(request: BigQueryDatasetRequest):
    """Get full metadata for a BigQuery dataset"""
    if not connections["bigquery"]:
        raise HTTPException(status_code=400, detail="Not connected to BigQuery")
    return connections["bigquery"].get_dataset_metadata(request.dataset_id)


# ============== POSTGRESQL ENDPOINTS ==============

@router.get("/postgresql/schemas")
async def get_pg_schemas():
    """List all PostgreSQL schemas"""
    if not connections["postgresql"]:
        raise HTTPException(status_code=400, detail="Not connected to PostgreSQL")
    return connections["postgresql"].get_schemas()


@router.post("/postgresql/tables")
async def get_pg_tables(request: PostgreSQLSchemaRequest):
    """List tables in a PostgreSQL schema"""
    if not connections["postgresql"]:
        raise HTTPException(status_code=400, detail="Not connected to PostgreSQL")
    return connections["postgresql"].get_tables(request.schema)


@router.post("/postgresql/columns")
async def get_pg_columns(request: PostgreSQLSchemaRequest):
    """Get columns for all tables in a PostgreSQL schema"""
    if not connections["postgresql"]:
        raise HTTPException(status_code=400, detail="Not connected to PostgreSQL")
    tables = connections["postgresql"].get_tables(request.schema)
    result = []
    for t in tables[:30]:
        cols = connections["postgresql"].get_columns(request.schema, t["table_name"])
        result.append({"table_name": t["table_name"], "table_type": t["table_type"], "columns": cols})
    return result


@router.post("/postgresql/foreign-keys")
async def get_pg_foreign_keys(request: PostgreSQLSchemaRequest):
    """Get foreign key relationships"""
    if not connections["postgresql"]:
        raise HTTPException(status_code=400, detail="Not connected to PostgreSQL")
    return connections["postgresql"].get_foreign_keys(request.schema)


@router.post("/postgresql/schema-metadata")
async def get_pg_schema_metadata(request: PostgreSQLSchemaRequest):
    """Get full metadata for a PostgreSQL schema"""
    if not connections["postgresql"]:
        raise HTTPException(status_code=400, detail="Not connected to PostgreSQL")
    return connections["postgresql"].get_schema_metadata(request.schema)


# ============== GCS ENDPOINTS ==============

@router.get("/gcs/buckets")
async def get_gcs_buckets():
    """List all GCS buckets"""
    if not connections["gcs"]:
        raise HTTPException(status_code=400, detail="Not connected to GCS")
    return connections["gcs"].get_buckets()


@router.post("/gcs/blobs")
async def get_gcs_blobs(request: GCSBucketRequest):
    """List blobs in a GCS bucket"""
    if not connections["gcs"]:
        raise HTTPException(status_code=400, detail="Not connected to GCS")
    return connections["gcs"].get_blobs(request.bucket_name, prefix=request.prefix)


@router.post("/gcs/csv-header")
async def get_gcs_csv_header(request: GCSBlobRequest):
    """Read CSV file header from GCS"""
    if not connections["gcs"]:
        raise HTTPException(status_code=400, detail="Not connected to GCS")
    return connections["gcs"].read_csv_header(request.bucket_name, request.blob_name)


@router.post("/gcs/json-structure")
async def get_gcs_json_structure(request: GCSBlobRequest):
    """Read JSON file structure from GCS"""
    if not connections["gcs"]:
        raise HTTPException(status_code=400, detail="Not connected to GCS")
    return connections["gcs"].read_json_structure(request.bucket_name, request.blob_name)


@router.post("/gcs/bucket-metadata")
async def get_gcs_bucket_metadata(request: GCSBucketRequest):
    """Get summary metadata for a GCS bucket"""
    if not connections["gcs"]:
        raise HTTPException(status_code=400, detail="Not connected to GCS")
    return connections["gcs"].get_bucket_metadata(request.bucket_name, prefix=request.prefix)


# ============== SPEC GENERATION ENDPOINTS ==============

@router.post("/generate-spec")
async def generate_spec(request: RepoRequest):
    """Generate a specification document from a GitHub repository"""
    if not connections["github"]:
        raise HTTPException(status_code=400, detail="Not connected to GitHub")

    metadata = connections["github"].get_repo_metadata(request.owner, request.repo_name)
    if not metadata:
        raise HTTPException(status_code=404, detail="Repository not found")

    agent = SpecAgent()
    spec = agent.generate_spec(metadata)
    specs_cache[request.repo_name] = spec
    return {"repo_name": request.repo_name, "spec": spec}


# ============== CHAT ENDPOINTS ==============

@router.post("/chat")
async def chat(request: ChatRequest):
    """Chat with the AI about specifications and data contracts, with chat history support"""
    context = ""
    if request.repo_name and request.repo_name in specs_cache:
        context = specs_cache[request.repo_name]
    elif specs_cache:
        context = "\n\n---\n\n".join(specs_cache.values())

    agent = SpecAgent()
    chat_result = agent.chat(
        question=request.question,
        user_id="anonymous",
        repo_name=request.repo_name,
        context=context
    )
    return {
        "question": request.question,
        "response": chat_result["answer"],
        "history": chat_result["history"]
    }


# ============== HEALTH CHECK ==============

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "llm_provider": settings.llm_provider}
