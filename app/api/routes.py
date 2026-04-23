"""
API Routes for Spec Generator
All connections are initiated from the frontend (no hardcoded tokens).
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
from app.mcp_servers.github_server import GitHubMCPServer
from app.mcp_servers.powerbi_server import PowerBIMCPServer
from app.mcp_servers.bigquery_server import BigQueryMCPServer
from app.mcp_servers.postgresql_server import PostgreSQLMCPServer
from app.mcp_servers.gcs_server import GCSMCPServer
from app.agents.spec_agent import SpecAgent
from app.agents.orchestrator_agent import OrchestratorAgent
from app.config.settings import settings
"""from app.auth_sso import get_current_user, require_role"""
from app.db import SessionLocal
from app.models import Project, Source
import json
import uuid as _uuid
from datetime import datetime as _dt

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


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============== HEALTH CHECK & TEST ENDPOINTS ==============

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


@router.post("/test/vectorstore/init")
async def test_vectorstore_init():
    """Test endpoint to initialize vector store and create data folder"""
    try:
        from app.vectorstore import get_vector_manager
        manager = get_vector_manager()
        
        # Test adding a simple template to trigger folder creation
        result = manager.add_template(
            template_text="Test template for initialization",
            template_title="Vector Store Init Test",
            project_id="test"
        )
        
        import os
        data_dir_exists = os.path.exists("./data/chroma")
        
        return {
            "status": "success",
            "message": "Vector store initialized",
            "data_folder_exists": data_dir_exists,
            "template_result": result
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


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


# ============== PROJECT REQUEST/RESPONSE MODELS ==============

class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class AddSourceRequest(BaseModel):
    type: str        # github, pdf, notion, googledoc, text, api, url, database, bigquery, postgresql, powerbi, gcs
    label: str = ""
    config: dict = {}  # type-specific config (url, content, etc.)


class PipelineConfirmPlaceholdersRequest(BaseModel):
    placeholders: list  # confirmed/edited placeholders [{id, label, section, type, ...}]


class PipelineConfirmValuesRequest(BaseModel):
    values: dict  # confirmed {field_id: value}


class PipelineApproveSpecRequest(BaseModel):
    spec_markdown: str  # the final approved spec text


class ProjectChatRequest(BaseModel):
    question: str
    pipeline_step: str = ""   # current step name
    placeholders: list = []   # confirmed placeholders (if past step 1)
    extracted_values: dict = {}  # confirmed values (if past step 2)


class ExportRequest(BaseModel):
    format: str = "markdown"  # markdown, json


# ============== VECTOR STORE REQUEST/RESPONSE MODELS ==============

class AddTemplateRequest(BaseModel):
    template_text: str
    template_title: str = "Template"


class SearchTemplatesRequest(BaseModel):
    query: str
    top_k: int = 5


class AddRepositoryFileRequest(BaseModel):
    file_content: str
    file_path: str
    file_type: str  # python, sql, markdown, yaml, json, etc.


class SearchRepositoryContentRequest(BaseModel):
    query: str
    top_k: int = 10
    file_type: Optional[str] = None


class RepositoryFilesRequest(BaseModel):
    files: list[dict]  # List of {content, path, type}


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


@router.post("/generate-spec-from-template")
async def generate_spec_from_template(
    owner: str = Form(...),
    repo_name: str = Form(...),
    template_file: UploadFile = File(...),
):
    """
    Generate a specification by filling an uploaded template (PDF or Markdown)
    with data extracted from a GitHub repository using the multi-agent pipeline.
    Supports: .pdf, .md, .txt files.
    """
    if not connections["github"]:
        raise HTTPException(status_code=400, detail="Not connected to GitHub")

    # Read file bytes (works for both PDF and text)
    file_bytes = await template_file.read()
    filename = template_file.filename or "template.md"

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Template file is empty.")

    # Fetch repo metadata
    metadata = connections["github"].get_repo_metadata(owner, repo_name)
    if not metadata:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Run multi-agent pipeline (handles PDF/text internally)
    orchestrator = OrchestratorAgent()
    result = orchestrator.generate(file_bytes, filename, metadata)

    # Cache the generated spec
    specs_cache[repo_name] = result["spec"]

    return {
        "repo_name": repo_name,
        "spec": result["spec"],
        "template_title": result.get("template_title", ""),
        "sections": result.get("sections", []),
        "fields": result.get("fields", []),
        "extracted_values": result.get("extracted_values", {}),
        "validation": result["validation"],
    }


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


# ============== PIPELINE ENDPOINTS (step-by-step with validation gates) ==============

# In-memory pipeline state per project
_pipeline_state = {}  # project_id -> {step, template_text, placeholders, values, spec, validation}


def _get_source_content_for_project(project_id: str, db) -> str:
    """Gather content snippets from all connected sources for a project."""
    # TODO: Implement source management in database
    # For now, return empty since sources aren't persisted yet
    return ""


def _build_datasource_context() -> str:
    """
    Pull live schema and content from all currently connected data sources.
    Returns a rich text block injected into the LLM context for extraction and chat.
    """
    parts = []

    # ── BigQuery ──────────────────────────────────────────────────────────────
    bq = connections.get("bigquery")
    if bq and bq.connected:
        try:
            datasets = bq.get_datasets()
            parts.append(f"### BigQuery (project: {bq.project_id})")
            parts.append(f"Datasets disponibles: {[d['dataset_id'] for d in datasets]}")
            for ds in datasets[:5]:
                did = ds["dataset_id"]
                try:
                    tables = bq.get_tables(did)
                    parts.append(f"\n#### Dataset: {did}")
                    for tbl in tables[:20]:
                        tid = tbl["table_id"]
                        try:
                            schema = bq.get_table_schema(did, tid)
                            cols = schema.get("columns", [])
                            col_summary = ", ".join(
                                f"{c['name']} ({c['type']})" for c in cols[:30]
                            )
                            rows = schema.get("num_rows", "?")
                            parts.append(
                                f"  Table `{did}.{tid}` [{tbl['table_type']}] "
                                f"— {rows} lignes — colonnes: {col_summary}"
                            )
                        except Exception:
                            parts.append(f"  Table `{did}.{tid}` — schema indisponible")
                except Exception:
                    parts.append(f"  Dataset {did} — tables indisponibles")
        except Exception as e:
            parts.append(f"### BigQuery — erreur: {e}")

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    pg = connections.get("postgresql")
    if pg and pg.connected:
        try:
            schemas = pg.get_schemas()
            parts.append(f"\n### PostgreSQL ({pg.database}@{pg.host})")
            parts.append(f"Schémas: {[s['schema_name'] for s in schemas]}")
            for schema_row in schemas[:3]:
                schema_name = schema_row["schema_name"]
                try:
                    tables = pg.get_tables(schema_name)
                    parts.append(f"\n#### Schéma: {schema_name}")
                    for tbl in tables[:30]:
                        tname = tbl["table_name"]
                        try:
                            cols = pg.get_columns(schema_name, tname)
                            col_summary = ", ".join(
                                f"{c['column_name']} ({c['data_type']})" for c in cols[:30]
                            )
                            parts.append(f"  Table `{schema_name}.{tname}` — colonnes: {col_summary}")
                        except Exception:
                            parts.append(f"  Table `{schema_name}.{tname}` — colonnes indisponibles")
                    try:
                        fks = pg.get_foreign_keys(schema_name)
                        if fks:
                            fk_lines = [
                                f"{r['source_table']}.{r['source_column']} → {r['target_table']}.{r['target_column']}"
                                for r in fks[:20]
                            ]
                            parts.append(f"  Clés étrangères: {'; '.join(fk_lines)}")
                    except Exception:
                        pass
                except Exception:
                    parts.append(f"  Schéma {schema_name} — tables indisponibles")
        except Exception as e:
            parts.append(f"### PostgreSQL — erreur: {e}")

    # ── GCS ───────────────────────────────────────────────────────────────────
    gcs = connections.get("gcs")
    if gcs and gcs.connected:
        try:
            buckets = gcs.get_buckets()
            parts.append(f"\n### GCS (project: {gcs.project_id})")
            parts.append(f"Buckets: {[b['name'] for b in buckets]}")
            for bucket in buckets[:3]:
                bname = bucket["name"]
                try:
                    blobs = gcs.get_blobs(bname, max_results=50)
                    file_summary = ", ".join(
                        f"{b['name']} ({b.get('file_type','?')})" for b in blobs[:20]
                    )
                    parts.append(f"  Bucket `{bname}`: {file_summary}")
                    # Try reading headers of first CSV found
                    for blob in blobs[:10]:
                        if blob.get("file_type") == "csv":
                            try:
                                header = gcs.read_csv_header(bname, blob["name"])
                                cols = header.get("columns", [])
                                parts.append(
                                    f"    CSV `{blob['name']}` — colonnes: {', '.join(str(c) for c in cols[:30])}"
                                )
                            except Exception:
                                pass
                            break
                except Exception:
                    parts.append(f"  Bucket `{bname}` — contenu indisponible")
        except Exception as e:
            parts.append(f"### GCS — erreur: {e}")

    # ── Power BI ──────────────────────────────────────────────────────────────
    pbi = connections.get("powerbi")
    if pbi and pbi.connected:
        try:
            workspaces = pbi.get_workspaces()
            parts.append(f"\n### Power BI")
            for ws in workspaces[:5]:
                wsid = ws.get("id", "")
                wsname = ws.get("name", wsid)
                try:
                    datasets = pbi.get_datasets(wsid)
                    reports = pbi.get_reports(wsid)
                    parts.append(
                        f"  Workspace `{wsname}`: {len(datasets)} datasets, {len(reports)} reports"
                    )
                    for ds in datasets[:5]:
                        parts.append(f"    Dataset: {ds.get('name','?')}")
                    for rpt in reports[:5]:
                        parts.append(f"    Report: {rpt.get('name','?')}")
                except Exception:
                    parts.append(f"  Workspace `{wsname}` — détails indisponibles")
        except Exception as e:
            parts.append(f"### Power BI — erreur: {e}")

    # ── GitHub ─────────────────────────────────────────────────────────────────
    gh = connections.get("github")
    if gh and gh.connected:
        try:
            user = gh.client.get_user()
            parts.append(f"\n### GitHub (user: {user.login})")
            repos = list(user.get_repos(sort="updated"))[:10]
            parts.append(f"Repos récents: {[r.name for r in repos]}")
        except Exception as e:
            parts.append(f"### GitHub — erreur: {e}")

    if not parts:
        return "Aucune source de données connectée."

    return "\n".join(parts)


@router.post("/projects/{project_id}/pipeline/template")
async def pipeline_step_template(
    project_id: str,
    template_file: UploadFile = File(...),
    db=Depends(get_db),
):
    """Step 1: Parse template, extract placeholders using TemplateAgent."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    file_bytes = await template_file.read()
    filename = template_file.filename or "template.md"
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Template file is empty.")

    from app.agents.template_agent import TemplateAgent
    agent = TemplateAgent()
    template_text = agent.read_file(file_bytes, filename)
    if not template_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from template.")

    detected = agent.detect_fields(template_text)
    fields = detected.get("fields", [])

    # Store pipeline state
    _pipeline_state[project_id] = {
        "step": "template",
        "template_text": template_text,
        "template_title": detected.get("template_title", ""),
        "sections": detected.get("sections", []),
        "placeholders": fields,
        "values": {},
        "spec": "",
        "validation": None,
    }

    return {
        "template_title": detected.get("template_title", ""),
        "sections": detected.get("sections", []),
        "placeholders": fields,
    }


@router.post("/projects/{project_id}/pipeline/extract")
async def pipeline_step_extract(
    project_id: str,
    req: PipelineConfirmPlaceholdersRequest,
    db=Depends(get_db),
):
    """Step 2: With confirmed placeholders, extract values from all connected sources."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    state = _pipeline_state.get(project_id)
    if not state:
        raise HTTPException(status_code=400, detail="Run template step first.")

    # Save confirmed placeholders
    state["placeholders"] = req.placeholders
    state["step"] = "extract"

    # Gather source content as a pseudo-metadata dict
    source_content = _get_source_content_for_project(project_id, db)

    # Build live data source schema context from all connected sources
    datasource_context = _build_datasource_context()

    metadata = {
        "repo_name": p.name,
        "owner": "",
        "description": p.description or "",
        "readme": source_content,
        "languages": "",
        "topics": "",
        "structure": {},
        "sql_files": [],
        "python_files": [],
        "yaml_files": [],
        "json_files": [],
        "notebook_files": [],
        "datasource_context": datasource_context,
    }

    from app.agents.extraction_agent import ExtractionAgent
    agent = ExtractionAgent()
    extracted = agent.extract(metadata, req.placeholders)

    # Build per-field result with confidence heuristic
    results = []
    for field in req.placeholders:
        fid = field["id"]
        value = extracted.get(fid, "")
        lower_val = value.strip().lower() if value else ""
        if not lower_val or lower_val in ("non identifié", "n/a", ""):
            confidence = "low"
        elif len(value.strip()) < 10:
            confidence = "medium"
        else:
            confidence = "high"

        source_label = p.name if p else "Sources"  # Use project name as source

        results.append({
            "id": fid,
            "label": field.get("label", fid),
            "section": field.get("section", ""),
            "type": field.get("type", "text"),
            "value": value,
            "confidence": confidence,
            "source": source_label,
        })

    state["values"] = extracted
    state["extraction_results"] = results

    return {"results": results}


@router.post("/projects/{project_id}/pipeline/map")
async def pipeline_step_map(
    project_id: str,
    req: PipelineConfirmValuesRequest,
    db=Depends(get_db),
):
    """Step 3: With confirmed values, compose the final spec via MappingAgent."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    state = _pipeline_state.get(project_id)
    if not state:
        raise HTTPException(status_code=400, detail="Run extract step first.")

    state["values"] = req.values
    state["step"] = "map"

    from app.agents.mapping_agent import MappingAgent
    agent = MappingAgent()
    spec = agent.compose(
        template_text=state["template_text"],
        extracted_values=req.values,
        fields=state["placeholders"],
    )

    # Run validation
    from app.agents.validation_agent import ValidationAgent
    validator = ValidationAgent()
    validation = validator.validate(state["placeholders"], req.values)

    state["spec"] = spec
    state["validation"] = validation

    return {
        "spec": spec,
        "validation": validation,
    }


# ============== VECTOR STORE ENDPOINTS ==============
# Separate endpoints for templates and repository content chunking/retrieval

@router.post("/vectorstore/stats")
async def get_vectorstore_stats():
    """Get statistics about the vector stores."""
    from app.vectorstore import get_vector_manager
    manager = get_vector_manager()
    return manager.get_statistics()


# ──────────────────── TEMPLATES ────────────────────────────

@router.post("/projects/{project_id}/vectorstore/templates/add")
async def add_template_to_vectorstore(
    project_id: str,
    request: AddTemplateRequest,
    db=Depends(get_db),
):
    """
    Add a template to the vector store.
    Chunks the template and stores all chunks with embeddings.
    """
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    
    from app.vectorstore import get_vector_manager
    manager = get_vector_manager()
    
    result = manager.add_template(
        template_text=request.template_text,
        template_title=request.template_title,
        project_id=project_id,
    )
    
    return {
        "status": "success",
        "message": f"Template added: {result['chunks_added']} chunks created",
        **result
    }


@router.post("/projects/{project_id}/vectorstore/templates/search")
async def search_templates_in_vectorstore(
    project_id: str,
    request: SearchTemplatesRequest,
    db=Depends(get_db),
):
    """
    Search for templates similar to a query.
    Returns top-k most similar template chunks.
    """
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    
    from app.vectorstore import get_vector_manager
    manager = get_vector_manager()
    
    results = manager.search_templates(
        query=request.query,
        project_id=project_id,
        top_k=request.top_k,
    )
    
    return {
        "query": request.query,
        "results_count": len(results),
        "results": results,
    }


@router.get("/projects/{project_id}/vectorstore/templates/list")
async def list_project_templates(project_id: str):
    """
    Get all templates for a project.
    """
    from app.vectorstore import get_vector_manager
    manager = get_vector_manager()
    
    templates = manager.get_all_templates(project_id)
    
    return {
        "project_id": project_id,
        "templates_count": len(templates),
        "templates": templates,
    }


# ──────────────────── REPOSITORY CONTENT ────────────────────────────

@router.post("/projects/{project_id}/vectorstore/content/add")
async def add_repository_file_to_vectorstore(
    project_id: str,
    repo_name: str,
    request: AddRepositoryFileRequest,
    db=Depends(get_db),
):
    """
    Add a repository file to the vector store.
    Chunks the file based on its type and stores all chunks with embeddings.
    """
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    
    from app.vectorstore import get_vector_manager
    manager = get_vector_manager()
    
    result = manager.add_repository_content(
        file_content=request.file_content,
        file_path=request.file_path,
        file_type=request.file_type,
        project_id=project_id,
        repo_name=repo_name,
    )
    
    return {
        "status": "success",
        "message": f"File added: {result['chunks_added']} chunks created",
        **result
    }


@router.post("/projects/{project_id}/vectorstore/content/add-multiple")
async def add_multiple_repository_files_to_vectorstore(
    project_id: str,
    repo_name: str,
    request: RepositoryFilesRequest,
    db=Depends(get_db),
):
    """
    Add multiple repository files to the vector store at once.
    """
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    
    from app.vectorstore import get_vector_manager
    manager = get_vector_manager()
    
    results = manager.add_multiple_repository_files(
        files=request.files,
        project_id=project_id,
        repo_name=repo_name,
    )
    
    return {
        "status": "success",
        "files_processed": len(request.files),
        "results": results,
    }


@router.post("/projects/{project_id}/vectorstore/content/search")
async def search_repository_content_in_vectorstore(
    project_id: str,
    request: SearchRepositoryContentRequest,
    db=Depends(get_db),
):
    """
    Search for repository content similar to a query.
    Returns top-k most similar content chunks.
    """
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    
    from app.vectorstore import get_vector_manager
    manager = get_vector_manager()
    
    results = manager.search_repository_content(
        query=request.query,
        project_id=project_id,
        top_k=request.top_k,
        file_type=request.file_type,
    )
    
    return {
        "query": request.query,
        "results_count": len(results),
        "results": results,
    }


@router.get("/projects/{project_id}/vectorstore/content/list")
async def list_project_repository_content(project_id: str):
    """
    Get all repository content chunks for a project.
    """
    from app.vectorstore import get_vector_manager
    manager = get_vector_manager()
    
    content = manager.get_all_repository_content(project_id)
    
    total_chunks = sum(len(f.get("chunks", [])) for f in content)
    
    return {
        "project_id": project_id,
        "files_count": len(content),
        "total_chunks": total_chunks,
        "files": content,
    }


@router.get("/projects/{project_id}/vectorstore/content/file/{file_id}")
async def get_full_repository_file(project_id: str, file_id: str):
    """
    Reconstruct and get the full content of a file from chunks.
    """
    from app.vectorstore import get_vector_manager
    manager = get_vector_manager()
    
    file_data = manager.get_file_content(file_id)
    
    if not file_data:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")
    
    return file_data


@router.delete("/projects/{project_id}/vectorstore/clear")
async def clear_project_vectorstore(project_id: str):
    """
    Clear all vector store data for a project (both templates and content).
    """
    from app.vectorstore import get_vector_manager
    manager = get_vector_manager()
    
    result = manager.clear_project(project_id)
    
    return {
        "status": "success",
        "message": "Vector store cleared for project",
        **result
    }


# ──────────────────── INTEGRATED REPOSITORY EMBEDDING ────────────────────────────

@router.post("/projects/{project_id}/vectorstore/github/embed")
async def embed_github_repository(
    project_id: str,
    owner: str,
    repo_name: str,
    db=Depends(get_db),
):
    """
    Fetch a GitHub repository and embed all its content files into the vector store.
    This will extract and chunk:
    - README
    - Python files
    - SQL files
    - YAML/JSON config files
    - Notebooks
    """
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if not connections["github"]:
        raise HTTPException(status_code=400, detail="Not connected to GitHub")
    
    from app.vectorstore import get_vector_manager
    
    # Fetch repo metadata
    try:
        metadata = connections["github"].get_repo_metadata(owner, repo_name)
        if not metadata:
            raise HTTPException(status_code=404, detail="Repository not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching repository: {str(e)}")
    
    manager = get_vector_manager()
    
    # Collect all files to add
    files_to_add = []
    
    # Add README
    if metadata.get("readme"):
        files_to_add.append({
            "content": metadata["readme"],
            "path": "README.md",
            "type": "markdown"
        })
    
    # Add Python files
    for py_file in metadata.get("python_files", []):
        files_to_add.append({
            "content": py_file.get("content", ""),
            "path": py_file.get("path", ""),
            "type": "python"
        })
    
    # Add SQL files
    for sql_file in metadata.get("sql_files", []):
        files_to_add.append({
            "content": sql_file.get("content", ""),
            "path": sql_file.get("path", ""),
            "type": "sql"
        })
    
    # Add YAML files
    for yaml_file in metadata.get("yaml_files", []):
        files_to_add.append({
            "content": yaml_file.get("content", ""),
            "path": yaml_file.get("path", ""),
            "type": "yaml"
        })
    
    # Add JSON files
    for json_file in metadata.get("json_files", []):
        files_to_add.append({
            "content": json_file.get("content", ""),
            "path": json_file.get("path", ""),
            "type": "json"
        })
    
    # Add Notebook files
    for nb_file in metadata.get("notebook_files", []):
        files_to_add.append({
            "content": nb_file.get("content", ""),
            "path": nb_file.get("path", ""),
            "type": "notebook"
        })
    
    # Add all files to vector store
    results = manager.add_multiple_repository_files(
        files=files_to_add,
        project_id=project_id,
        repo_name=repo_name,
    )
    
    # Count successful additions
    successful = sum(1 for r in results if "error" not in r)
    
    return {
        "status": "success",
        "message": f"Repository embedded: {successful}/{len(files_to_add)} files processed",
        "repo_name": repo_name,
        "owner": owner,
        "files_processed": len(files_to_add),
        "files_successful": successful,
        "details": results,
    }



@router.post("/projects/{project_id}/pipeline/export")
async def pipeline_step_export(project_id: str, req: ExportRequest, db=Depends(get_db)):
    """Step 4: Return the finalized spec in the requested format."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    
    state = _pipeline_state.get(project_id)
    if not state or not state.get("spec"):
        raise HTTPException(status_code=400, detail="No spec to export. Complete the pipeline first.")

    spec_text = state["spec"]
    fmt = req.format.lower()

    if fmt == "json":
        return {
            "format": "json",
            "data": {
                "title": state.get("template_title", "Specification"),
                "sections": state.get("sections", []),
                "placeholders": state.get("placeholders", []),
                "values": state.get("values", {}),
                "spec_markdown": spec_text,
                "validation": state.get("validation"),
            }
        }
    else:
        return {
            "format": "markdown",
            "data": spec_text,
        }


@router.get("/projects/{project_id}/pipeline/state")
async def pipeline_get_state(project_id: str):
    """Get current pipeline state for a project."""
    state = _pipeline_state.get(project_id)
    if not state:
        return {"step": None}
    return {
        "step": state.get("step"),
        "template_title": state.get("template_title", ""),
        "placeholders": state.get("placeholders", []),
        "extraction_results": state.get("extraction_results", []),
        "values": state.get("values", {}),
        "spec": state.get("spec", ""),
        "validation": state.get("validation"),
    }


@router.post("/projects/{project_id}/chat")
async def project_chat(project_id: str, req: ProjectChatRequest, db=Depends(get_db)):
    """Project-aware chat powered by gpt-4o-mini with full context injection."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    state = _pipeline_state.get(project_id, {})

    # Gather source snippets (TODO: implement source persistence in DB)
    source_lines = []
    sources_text = "No sources connected."

    # Build live data source context (real schemas, tables, files from connected sources)
    live_datasource_context = _build_datasource_context()

    # Build system prompt with full pipeline context
    system_parts = [
        "You are a helpful data engineering assistant for a spec-generation platform called Jems Spec Generator.",
        "You have access to the real schemas, tables, and content of the connected data sources listed below.",
        "Use this information to answer questions precisely — reference actual table names, column names, and data structures when relevant.",
        f"Current project: {p.name}",
        f"Project description: {p.description or 'N/A'}",
        f"Connected sources (project config):\n{sources_text}",
        f"Live data source context (real schemas and content):\n{live_datasource_context}",
        f"Current pipeline step: {req.pipeline_step or state.get('step', 'none')}",
    ]
    if req.placeholders:
        ph_text = json.dumps(req.placeholders[:30], ensure_ascii=False)[:2000]
        system_parts.append(f"Confirmed placeholders: {ph_text}")
    if req.extracted_values:
        val_text = json.dumps(req.extracted_values, ensure_ascii=False)[:2000]
        system_parts.append(f"Confirmed extracted values: {val_text}")
    if state.get("spec"):
        system_parts.append(f"Current spec preview (first 2000 chars):\n{state['spec'][:2000]}")

    system_parts.append("Answer concisely. If you can reference specific source content, do so and tag your answer as [from sources]. Otherwise tag as [general].")

    system_prompt = "\n\n".join(system_parts)

    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": req.question},
        ],
    )
    answer = response.choices[0].message.content

    # Detect mode tag
    mode = "sources" if "[from sources]" in answer.lower() else "general"

    return {
        "answer": answer,
        "mode": mode,
    }


# ============== PROJECT ENDPOINTS ==============

@router.get("/projects")
async def list_projects(db=Depends(get_db)):
    """List all projects (newest first)"""
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return {
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "created_at": p.created_at.isoformat() if p.created_at else "",
                "sources": [
                    {
                        "id": s.id,
                        "type": s.type,
                        "type_name": s.type_name,
                        "icon": s.icon,
                        "label": s.label,
                        "config": s.config,
                        "status": s.status,
                        "added_at": s.added_at.isoformat() if s.added_at else "",
                    }
                    for s in p.sources
                ],
            }
            for p in projects
        ]
    }


@router.post("/projects")
async def create_project(req: CreateProjectRequest, db=Depends(get_db)):
    """Create a new project"""
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")
    
    project = Project(
        id=_uuid.uuid4().hex[:12],
        name=name,
        description=req.description.strip()
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at.isoformat() if project.created_at else "",
        "sources": [],
    }


@router.get("/projects/{project_id}")
async def get_project(project_id: str, db=Depends(get_db)):
    """Get a single project by ID"""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "created_at": p.created_at.isoformat() if p.created_at else "",
        "sources": [
            {
                "id": s.id,
                "type": s.type,
                "type_name": s.type_name,
                "icon": s.icon,
                "label": s.label,
                "config": s.config,
                "status": s.status,
                "added_at": s.added_at.isoformat() if s.added_at else "",
            }
            for s in p.sources
        ],
    }


@router.put("/projects/{project_id}")
async def update_project(project_id: str, req: UpdateProjectRequest, db=Depends(get_db)):
    """Update project name/description"""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if req.name is not None:
        p.name = req.name.strip()
    if req.description is not None:
        p.description = req.description.strip()
    
    db.commit()
    db.refresh(p)
    
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "created_at": p.created_at.isoformat() if p.created_at else "",
        "sources": [
            {
                "id": s.id,
                "type": s.type,
                "type_name": s.type_name,
                "icon": s.icon,
                "label": s.label,
                "config": s.config,
                "status": s.status,
                "added_at": s.added_at.isoformat() if s.added_at else "",
            }
            for s in p.sources
        ],
    }


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, db=Depends(get_db)):
    """Delete a project"""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    
    db.delete(p)
    db.commit()
    
    return {"ok": True}


# ============== PROJECT SOURCE ENDPOINTS ==============

SOURCE_TYPES = {
    "github":     {"name": "GitHub Repo",   "icon": "github"},
    "pdf":        {"name": "PDF File",      "icon": "file-text"},
    "notion":     {"name": "Notion Page",   "icon": "book-open"},
    "googledoc":  {"name": "Google Doc",    "icon": "file-spreadsheet"},
    "text":       {"name": "Plain Text",    "icon": "align-left"},
    "api":        {"name": "REST API",      "icon": "zap"},
    "url":        {"name": "Web URL",       "icon": "globe"},
    "database":   {"name": "DB Schema",     "icon": "database"},
    "bigquery":   {"name": "BigQuery",      "icon": "database"},
    "postgresql": {"name": "PostgreSQL",    "icon": "hard-drive"},
    "powerbi":    {"name": "Power BI",      "icon": "bar-chart-3"},
    "gcs":        {"name": "Cloud Storage", "icon": "cloud"},
}


@router.post("/projects/{project_id}/sources")
async def add_source(project_id: str, req: AddSourceRequest, db=Depends(get_db)):
    """Add a source to a project"""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    stype = req.type.lower()
    if stype not in SOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown source type: {stype}")

    meta = SOURCE_TYPES[stype]
    source = Source(
        id=_uuid.uuid4().hex[:12],
        project_id=project_id,
        type=stype,
        type_name=meta["name"],
        icon=meta["icon"],
        label=req.label.strip() or meta["name"],
        config=req.config or {},
        status="connected",
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    
    return {
        "id": source.id,
        "type": source.type,
        "type_name": source.type_name,
        "icon": source.icon,
        "label": source.label,
        "config": source.config,
        "status": source.status,
        "added_at": source.added_at.isoformat() if source.added_at else "",
    }


@router.delete("/projects/{project_id}/sources/{source_id}")
async def remove_source(project_id: str, source_id: str, db=Depends(get_db)):
    """Remove a source from a project"""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    
    source = db.query(Source).filter(
        Source.id == source_id,
        Source.project_id == project_id
    ).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    db.delete(source)
    db.commit()
    
    return {"ok": True}


@router.get("/source-types")
async def list_source_types():
    """List all available source types"""
    return {"types": [
        {"id": k, "name": v["name"], "icon": v["icon"]}
        for k, v in SOURCE_TYPES.items()
    ]}


# ============== HEALTH CHECK ==============

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "llm_provider": settings.llm_provider}
