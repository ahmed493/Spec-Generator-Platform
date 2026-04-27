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
from app.agents.pipeline_detection_agent import PipelineDetectionAgent
from app.config.settings import settings
"""from app.auth_sso import get_current_user, require_role"""
import json
import difflib
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

logger = logging.getLogger(__name__)

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

# ── Persist / restore connections across hot-reloads ─────────────────────────
import pathlib as _pathlib
import os as _os

_CREDS_FILE = _pathlib.Path(__file__).parent.parent / ".connections_cache.json"


def _save_credentials(key: str, creds: dict) -> None:
    """Persist connection credentials to a local JSON file."""
    try:
        data: dict = {}
        if _CREDS_FILE.exists():
            data = json.loads(_CREDS_FILE.read_text())
        data[key] = creds
        _CREDS_FILE.write_text(json.dumps(data, indent=2))
    except Exception as exc:
        logger.warning("Could not save credentials: %s", exc)


def _load_credentials(key: str) -> dict:
    """Load persisted credentials for a given key."""
    try:
        if _CREDS_FILE.exists():
            data = json.loads(_CREDS_FILE.read_text())
            return data.get(key, {})
    except Exception:
        pass
    return {}


def _restore_connections() -> None:
    """Called once on module load — reconnects using saved credentials."""
    # GitHub
    if connections["github"] is None:
        creds = _load_credentials("github")
        token = creds.get("token", "")
        if token:
            try:
                srv = GitHubMCPServer(token)
                if srv.connect():
                    connections["github"] = srv
                    logger.info("Auto-restored GitHub connection from cache")
            except Exception as exc:
                logger.warning("Failed to auto-restore GitHub: %s", exc)
    # PostgreSQL
    if connections["postgresql"] is None:
        creds = _load_credentials("postgresql")
        if creds:
            try:
                srv = PostgreSQLMCPServer(**creds)
                if srv.connect():
                    connections["postgresql"] = srv
                    logger.info("Auto-restored PostgreSQL connection from cache")
            except Exception as exc:
                logger.warning("Failed to auto-restore PostgreSQL: %s", exc)


_restore_connections()

# ============== PERSISTENT PROJECT STORE ==============
import uuid as _uuid
from datetime import datetime as _dt

_PROJECTS_FILE = _pathlib.Path(__file__).parent.parent / ".projects_cache.json"

_projects: dict = {}        # id -> project dict
_pipeline_state: dict = {}  # project_id -> pipeline detection state (pre-declared for load)


def _new_id():
    return _uuid.uuid4().hex[:12]


def _now():
    return _dt.utcnow().isoformat() + "Z"


def _persist_state() -> None:
    """Save _projects and _pipeline_state to disk so hot-reloads don't lose data."""
    try:
        _PROJECTS_FILE.write_text(json.dumps({
            "projects": _projects,
            "pipeline_state": _pipeline_state,
        }, indent=2, default=str))
    except Exception as exc:
        logger.warning("Could not persist state: %s", exc)


def _load_state() -> None:
    """Load persisted projects and pipeline state on startup."""
    global _projects, _pipeline_state
    try:
        if _PROJECTS_FILE.exists():
            data = json.loads(_PROJECTS_FILE.read_text())
            _projects.update(data.get("projects", {}))
            _pipeline_state.update(data.get("pipeline_state", {}))
            logger.info("Restored %d projects from disk", len(_projects))
    except Exception as exc:
        logger.warning("Could not restore state from disk: %s", exc)


_load_state()


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


class PipelineSelectRequest(BaseModel):
    pipeline_id: str


class PipelineUpdateRequest(BaseModel):
    pipelines: list


class PipelineSplitRequest(BaseModel):
    pipeline_id: str
    split_name_1: str
    split_name_2: str


class PipelineMergeRequest(BaseModel):
    pipeline_ids: list
    merged_name: str


class PipelineReorderRequest(BaseModel):
    pipeline_ids: list


class PipelineVersionDiffRequest(BaseModel):
    from_version_id: str
    to_version_id: str


class ProjectChatRequest(BaseModel):
    question: str
    pipeline_step: str = ""   # current step name
    placeholders: list = []   # confirmed placeholders (if past step 1)
    extracted_values: dict = {}  # confirmed values (if past step 2)


class ExportRequest(BaseModel):
    format: str = "markdown"  # markdown, json


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
        _save_credentials("github", {"token": request.token.strip()})
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


# ============== DATASOURCE CONTEXT HELPER ==============

def _collect_datasource_context() -> str:
    """
    Query every active non-GitHub connection and return a combined text
    summary of their schemas/metadata.  This is injected into the repo
    metadata dict so ExtractionAgent can use all connected sources.
    """
    parts = []

    # ── BigQuery ────────────────────────────────────────────────────────────
    if connections.get("bigquery"):
        try:
            bq = connections["bigquery"]
            result = bq.get_datasets()
            datasets = result.get("datasets", [])
            parts.append("### BigQuery")
            for ds in datasets[:10]:
                ds_id = ds.get("dataset_id") or ds.get("id", "")
                if not ds_id:
                    continue
                try:
                    meta = bq.get_dataset_metadata(ds_id)
                    tables = meta.get("tables", [])
                    for t in tables[:20]:
                        tname = t.get("table_id") or t.get("table_name", "")
                        cols = t.get("schema", t.get("columns", []))
                        col_str = ", ".join(
                            f"{c.get('name','?')} ({c.get('field_type', c.get('type','?'))})"
                            for c in cols[:30]
                        )
                        parts.append(f"  Table `{ds_id}.{tname}`: {col_str}")
                except Exception:
                    parts.append(f"  Dataset `{ds_id}` (schema unavailable)")
        except Exception as e:
            parts.append(f"### BigQuery (error: {e})")

    # ── PostgreSQL ──────────────────────────────────────────────────────────
    if connections.get("postgresql"):
        try:
            pg = connections["postgresql"]
            schemas_result = pg.get_schemas()
            schemas = schemas_result.get("schemas", ["public"])
            parts.append("### PostgreSQL")
            for schema in schemas[:5]:
                schema_name = schema if isinstance(schema, str) else schema.get("schema_name", "public")
                try:
                    meta = pg.get_schema_metadata(schema_name)
                    for t in meta.get("tables", [])[:20]:
                        tname = t.get("table_name", "")
                        cols = t.get("columns", [])
                        col_str = ", ".join(
                            f"{c.get('column_name','?')} ({c.get('data_type','?')})"
                            for c in cols[:30]
                        )
                        parts.append(f"  Table `{schema_name}.{tname}`: {col_str}")
                except Exception:
                    parts.append(f"  Schema `{schema_name}` (schema unavailable)")
        except Exception as e:
            parts.append(f"### PostgreSQL (error: {e})")

    # ── GCS ─────────────────────────────────────────────────────────────────
    if connections.get("gcs"):
        try:
            gcs = connections["gcs"]
            buckets_result = gcs.get_buckets()
            buckets = buckets_result.get("buckets", [])
            parts.append("### GCS (Google Cloud Storage)")
            for b in buckets[:5]:
                bname = b if isinstance(b, str) else b.get("name", "")
                if not bname:
                    continue
                try:
                    meta = gcs.get_bucket_metadata(bname)
                    blobs = meta.get("blobs", [])
                    blob_names = [bl.get("name", bl) if isinstance(bl, dict) else bl for bl in blobs[:20]]
                    parts.append(f"  Bucket `{bname}`: {', '.join(blob_names)}")
                except Exception:
                    parts.append(f"  Bucket `{bname}` (contents unavailable)")
        except Exception as e:
            parts.append(f"### GCS (error: {e})")

    # ── Power BI ────────────────────────────────────────────────────────────
    if connections.get("powerbi"):
        try:
            pbi = connections["powerbi"]
            ws_result = pbi.get_workspaces()
            workspaces = ws_result.get("workspaces", [])
            parts.append("### Power BI")
            for ws in workspaces[:5]:
                ws_id = ws.get("id", "")
                ws_name = ws.get("name", ws_id)
                if not ws_id:
                    continue
                try:
                    meta = pbi.get_workspace_metadata(ws_id)
                    datasets = meta.get("datasets", [])
                    reports = meta.get("reports", [])
                    ds_names = [d.get("name", "") for d in datasets[:10]]
                    rp_names = [r.get("name", "") for r in reports[:10]]
                    parts.append(f"  Workspace `{ws_name}` — Datasets: {', '.join(ds_names)} | Reports: {', '.join(rp_names)}")
                except Exception:
                    parts.append(f"  Workspace `{ws_name}` (metadata unavailable)")
        except Exception as e:
            parts.append(f"### Power BI (error: {e})")

    return "\n".join(parts)


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


# ============== PIPELINE DETECTION ENDPOINT ==============

@router.post("/detect-pipelines")
async def detect_pipelines(repos: str = Form(...)):
    """
    Analyse one or more GitHub repos (+ any active connections) and return
    the list of detected data pipelines / flux / modules with their names,
    descriptions, types and relevant source files / tables.
    """
    if not connections["github"]:
        raise HTTPException(status_code=400, detail="Not connected to GitHub")

    try:
        repo_list = json.loads(repos)
        if not isinstance(repo_list, list) or len(repo_list) == 0:
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="'repos' must be a non-empty JSON array of {owner, repo_name} objects."
        )

    metadata_list = []
    for entry in repo_list:
        repo_owner = entry.get("owner", "")
        repo_name = entry.get("repo_name", "")
        if not repo_owner or not repo_name:
            continue
        meta = connections["github"].get_repo_metadata(repo_owner, repo_name)
        if meta:
            metadata_list.append(meta)

    if not metadata_list:
        raise HTTPException(status_code=404, detail="None of the selected repositories could be found.")

    metadata = _merge_repo_metadata(metadata_list)

    # Enrich with connected source schemas
    datasource_context = _collect_datasource_context()
    if datasource_context:
        metadata["datasource_context"] = datasource_context

    agent = PipelineDetectionAgent()
    result = agent.detect(metadata)
    result["pipelines"] = [
        _normalize_detected_pipeline(p, i + 1)
        for i, p in enumerate(result.get("pipelines", []))
    ]
    result["count"] = len(result["pipelines"])
    return result


def _merge_repo_metadata(metadata_list: list[dict]) -> dict:
    """
    Merge metadata dicts from multiple GitHub repos into a single dict
    so ExtractionAgent sees all repos as one combined context.
    """
    if not metadata_list:
        return {}
    if len(metadata_list) == 1:
        return metadata_list[0]

    merged = {
        "repo_name": " + ".join(m.get("repo_name", "") for m in metadata_list),
        "owner": metadata_list[0].get("owner", ""),
        "description": " | ".join(
            m.get("description", "") for m in metadata_list if m.get("description")
        ),
        "languages": list({
            lang
            for m in metadata_list
            for lang in (m.get("languages") or [])
        }),
        "topics": list({
            t
            for m in metadata_list
            for t in (m.get("topics") or [])
        }),
        "readme": "\n\n---\n\n".join(
            f"## README — {m.get('repo_name', 'repo')}\n{m.get('readme', '')}"
            for m in metadata_list
            if m.get("readme")
        ),
    }

    # Merge all file-type lists
    for key in ("sql_files", "python_files", "yaml_files", "json_files", "notebook_files"):
        merged[key] = [f for m in metadata_list for f in (m.get(key) or [])]

    # Merge structure file lists
    all_files = [
        f
        for m in metadata_list
        for f in (m.get("structure", {}).get("files", []))
    ]
    merged["structure"] = {"files": all_files}

    return merged


@router.post("/generate-spec-from-template")
async def generate_spec_from_template(
    repos: str = Form(...),          # JSON: [{owner, repo_name}, ...]
    template_file: UploadFile = File(...),
    pipeline: str = Form(None),      # optional JSON: pipeline dict from PipelineDetectionAgent
):
    """
    Generate a specification by filling an uploaded template (PDF or Markdown)
    with data merged from one or more GitHub repositories and any other active
    data-source connections, using the multi-agent pipeline.
    Supports: .pdf, .md, .txt files.
    """
    if not connections["github"]:
        raise HTTPException(status_code=400, detail="Not connected to GitHub")

    # Parse repos list
    try:
        repo_list = json.loads(repos)
        if not isinstance(repo_list, list) or len(repo_list) == 0:
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="'repos' must be a non-empty JSON array of {owner, repo_name} objects.")

    # Read file bytes
    file_bytes = await template_file.read()
    filename = template_file.filename or "template.md"
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Template file is empty.")

    # Fetch and merge metadata for every selected repo
    metadata_list = []
    for entry in repo_list:
        repo_owner = entry.get("owner", "")
        repo_name = entry.get("repo_name", "")
        if not repo_owner or not repo_name:
            continue
        meta = connections["github"].get_repo_metadata(repo_owner, repo_name)
        if meta:
            metadata_list.append(meta)

    if not metadata_list:
        raise HTTPException(status_code=404, detail="None of the selected repositories could be found.")

    metadata = _merge_repo_metadata(metadata_list)

    # Collect schema/metadata from every other active connection and inject
    # it so ExtractionAgent can use all sources simultaneously, not just GitHub.
    datasource_context = _collect_datasource_context()
    if datasource_context:
        metadata["datasource_context"] = datasource_context

    # Parse optional pipeline context
    pipeline_dict = None
    if pipeline:
        try:
            pipeline_dict = json.loads(pipeline)
        except json.JSONDecodeError:
            pass

    # Run multi-agent pipeline (handles PDF/text internally)
    orchestrator = OrchestratorAgent()
    result = orchestrator.generate(file_bytes, filename, metadata, pipeline=pipeline_dict)

    # Cache the generated spec (key = all repo names joined)
    cache_key = "+".join(e.get("repo_name", "") for e in repo_list)
    specs_cache[cache_key] = result["spec"]

    return {
        "repo_name": cache_key,
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
# _pipeline_state is declared and loaded from disk in the persistent project store block above.


def _normalize_detected_pipeline(pipeline: dict, default_idx: int = 1) -> dict:
    pid = pipeline.get("id") or f"pipeline_{default_idx}"
    conf = pipeline.get("confidence", 0.5)
    try:
        conf = max(0.0, min(1.0, float(conf)))
    except Exception:
        conf = 0.5

    explainability = pipeline.get("explainability") or {}
    return {
        "id": pid,
        "name": pipeline.get("name") or pid,
        "category": pipeline.get("category") or "other",
        "description": pipeline.get("description") or "",
        "type": pipeline.get("type") or "other",
        "direction": pipeline.get("direction") or "internal",
        "source": pipeline.get("source") or "",
        "destination": pipeline.get("destination") or "",
        "class_name": pipeline.get("class_name") or pipeline.get("class") or "",
        "config_key": pipeline.get("config_key") or "",
        "queue_or_route": pipeline.get("queue_or_route") or "",
        "dependencies": pipeline.get("dependencies") or [],
        "execution_mode": pipeline.get("execution_mode") or "batch",
        "launcher": pipeline.get("launcher") or "unknown",
        "confidence": conf,
        "triggers": pipeline.get("triggers") or [],
        "listen_mode": pipeline.get("listen_mode") or [],
        "queues": pipeline.get("queues") or [],
        "jobs": pipeline.get("jobs") or [],
        "sub_pipelines": pipeline.get("sub_pipelines") or [],
        "parent_pipeline": pipeline.get("parent_pipeline"),
        "explainability": {
            "keywords": explainability.get("keywords") or [],
            "orchestration_clues": explainability.get("orchestration_clues") or [],
            "evidence_files": explainability.get("evidence_files") or (pipeline.get("source_files") or [])[:5],
            "evidence_tables": explainability.get("evidence_tables") or (pipeline.get("source_tables") or [])[:5],
        },
        "source_files": pipeline.get("source_files") or [],
        "source_tables": pipeline.get("source_tables") or [],
        "technologies": pipeline.get("technologies") or [],
    }


def _is_cicd_path(path: str) -> bool:
    p = (path or "").lower()
    if not p:
        return False
    cicd_path_markers = (
        ".gitlab-ci.yml",
        ".github/workflows/",
        "jenkinsfile",
        ".circleci/",
        ".azure-pipelines/",
        "bitbucket-pipelines",
        ".drone.yml",
        "docker-compose",
    )
    return any(marker in p for marker in cicd_path_markers)


def _is_cicd_pipeline(pipeline: dict) -> bool:
    source_files = pipeline.get("source_files") or []
    explainability = pipeline.get("explainability") or {}
    evidence_files = explainability.get("evidence_files") or []
    job_files = [j.get("file", "") for j in (pipeline.get("jobs") or []) if isinstance(j, dict)]
    paths = source_files + evidence_files + job_files

    path_cicd_hits = sum(1 for path in paths if _is_cicd_path(path))
    text_blob = " ".join([
        str(pipeline.get("name", "")),
        str(pipeline.get("description", "")),
        str(pipeline.get("launcher", "")),
        " ".join(str(c) for c in (explainability.get("orchestration_clues") or [])),
    ]).lower()
    cicd_text_markers = (
        "gitlab", "github actions", "jenkins", "ci/cd", "pipeline", "deploy",
        "build", "release", "merge request", "pull request", "stage",
    )
    text_hit = any(marker in text_blob for marker in cicd_text_markers)

    # Treat as CI/CD pipeline if evidence is mostly CI/CD files and context also looks CI/CD.
    return path_cicd_hits > 0 and text_hit


def _filter_cicd_only_pipelines(pipelines: list[dict]) -> tuple[list[dict], int]:
    if not pipelines:
        return pipelines, 0
    cicd = [p for p in pipelines if _is_cicd_pipeline(p)]
    non_cicd = [p for p in pipelines if not _is_cicd_pipeline(p)]

    # If real code/data pipelines exist, drop CI/CD-only entries.
    if non_cicd:
        removed = len(cicd)
        return non_cicd, removed

    return pipelines, 0


def _create_spec_version(project_id: str, state: dict, spec_text: str, validation: dict) -> dict:
    versions = state.setdefault("spec_versions", [])
    version_number = len(versions) + 1
    version = {
        "id": _new_id(),
        "project_id": project_id,
        "version_number": version_number,
        "status": "draft",
        "created_at": _now(),
        "spec": spec_text,
        "validation": validation,
    }
    versions.append(version)
    return version


def _get_source_content_for_project(project_id: str, lightweight: bool = False) -> str:
    """Gather content snippets from all connected sources for a project."""
    p = _projects.get(project_id)
    if not p:
        return ""
    parts = []
    for src in p.get("sources", []):
        cfg = src.get("config", {})
        stype = src.get("type", "")
        label = src.get("label", stype)
        # For GitHub sources, fetch repo metadata
        if stype == "github" and connections.get("github"):
            owner = cfg.get("owner", "")
            repo = cfg.get("repo", "")
            if owner and repo:
                try:
                    if lightweight:
                        readme = (
                            connections["github"].get_file_content(owner, repo, "README.md")
                            or connections["github"].get_file_content(owner, repo, "readme.md")
                            or ""
                        )[:1200]
                        parts.append(f"[Source: {label} (GitHub)]\nRepo: {owner}/{repo}\n{readme}")
                    else:
                        meta = connections["github"].get_repo_metadata(owner, repo)
                        readme = (meta.get("readme") or "")[:2000]
                        parts.append(f"[Source: {label} (GitHub)]\n{readme}")
                except Exception:
                    parts.append(f"[Source: {label} (GitHub)] — could not fetch metadata")
        elif stype == "text":
            parts.append(f"[Source: {label} (Text)]\n{cfg.get('content', '')[:2000]}")
        elif stype == "url":
            parts.append(f"[Source: {label} (URL)]\nURL: {cfg.get('url', '')}")
        elif stype == "api":
            parts.append(f"[Source: {label} (API)]\nEndpoint: {cfg.get('url', '')}")
        else:
            parts.append(f"[Source: {label} ({stype})] config={json.dumps(cfg)[:500]}")
    return "\n\n---\n\n".join(parts)


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


def _build_quick_datasource_context(project_id: str) -> str:
    """
    Source summary for pipeline detection.
    For database sources, fetches the actual table list so the agent can
    reason about what pipelines read/write to.
    """
    p = _projects.get(project_id)
    if not p:
        return ""

    parts = []
    for src in p.get("sources", []):
        stype = src.get("type", "unknown")
        label = src.get("label", stype)
        cfg = src.get("config", {})

        if stype == "github":
            owner = cfg.get("owner", "")
            repo = cfg.get("repo", "")
            if owner and repo:
                parts.append(f"GitHub source: {owner}/{repo} ({label})")
            else:
                parts.append(f"GitHub source: {label}")

        elif stype == "postgresql":
            conn = connections.get("postgresql")
            if conn and conn.connected:
                try:
                    schemas = conn.get_schemas()
                    table_lines = []
                    for schema_row in schemas[:8]:
                        sname = schema_row["schema_name"]
                        if sname in ("information_schema", "pg_catalog", "pg_toast"):
                            continue
                        tables = conn.get_tables(sname)
                        for t in tables[:40]:
                            table_lines.append(f"{sname}.{t['table_name']}")
                    parts.append(
                        f"PostgreSQL source ({label}):\n"
                        f"Tables ({len(table_lines)}): {', '.join(table_lines[:100])}"
                    )
                except Exception:
                    parts.append(f"PostgreSQL source: {label}")
            else:
                parts.append(f"PostgreSQL source: {label}")

        elif stype == "bigquery":
            conn = connections.get("bigquery")
            if conn and conn.connected:
                try:
                    datasets = conn.get_datasets()
                    table_lines = []
                    for ds in datasets[:8]:
                        did = ds["dataset_id"]
                        tables = conn.get_tables(did)
                        for t in tables[:30]:
                            table_lines.append(f"{did}.{t['table_id']}")
                    parts.append(
                        f"BigQuery source ({label}):\n"
                        f"Tables ({len(table_lines)}): {', '.join(table_lines[:100])}"
                    )
                except Exception:
                    parts.append(f"BigQuery source: {label}")
            else:
                parts.append(f"BigQuery source: {label}")

        elif stype == "gcs":
            parts.append(f"GCS source: {label}")
        elif stype == "powerbi":
            parts.append(f"Power BI source: {label}")
        else:
            parts.append(f"{stype} source: {label}")

    return "\n\n".join(parts)


def _get_repo_metadata_lightweight(owner: str, repo_name: str, preferred_branch: str | None = None) -> dict:
    """
    Lightweight repo metadata for pipeline detection.
    Uses a single git-tree API call to get all file paths, then selectively
    fetches content for pipeline-related files (DAGs, jobs, ETL scripts, configs).
    """
    gh = connections.get("github")
    if not gh:
        return {}

    repo = gh.get_repo(owner, repo_name)
    if not repo:
        return {}

    try:
        languages = list(dict(repo.get_languages()).keys())
    except Exception:
        languages = []

    try:
        topics = list(repo.get_topics())
    except Exception:
        topics = []

    # ── Fetch full file tree in ONE API call ─────────────────────────────────
    _PIPELINE_KEYWORDS = {
        # Generic pipeline terms
        "dag", "job", "pipeline", "workflow", "etl", "flow", "task",
        "ingest", "transform", "load", "extract", "process", "schedule",
        "trigger", "queue", "stream", "consumer", "producer", "connector",
        "sync", "batch", "cron", "spark", "airflow", "prefect", "dagster",
        "celery", "kafka", "rabbitmq", "pubsub", "sqs",
        # PHP / Symfony
        "command", "handler", "listener", "subscriber", "dispatcher",
        "messenger", "event", "worker", "import", "export", "migration",
        "fixture", "seeder", "schedule", "service",
        # Java / Spring
        "batch", "scheduler", "reader", "writer", "processor", "tasklet",
        "jms", "amqp", "activemq", "step", "itemreader", "itemwriter",
        # Node / TS
        "middleware", "hook", "subscriber", "emitter", "queue", "worker",
        "agenda", "bull", "bee", "kue",
        # General enterprise
        "integration", "adapter", "sink", "source", "bridge", "router",
        "replication", "propagat", "dispatch", "relay", "transfer",
    }
    _PIPELINE_DIRS = {
        "dags", "jobs", "pipelines", "workflows", "tasks", "flows",
        "airflow", "prefect", "dagster", "celery", "workers", "scripts",
        "etl", "src", "app", "config", "conf", "bin", "lib",
        # PHP / Symfony
        "command", "commands", "handler", "handlers", "listener", "listeners",
        "subscriber", "subscribers", "consumer", "consumers", "message",
        "messages", "event", "events", "service", "services", "import",
        "export", "migration", "migrations", "fixtures", "cron",
        # Java / Spring
        "batch", "scheduler", "reader", "writer", "processor",
        "integration", "adapter",
    }
    _CODE_EXTS = {
        # Python
        ".py",
        # PHP
        ".php",
        # Java / Kotlin / Scala
        ".java", ".kt", ".scala",
        # Go / .NET / Rust / Ruby / C/C++
        ".go", ".cs", ".rs", ".rb", ".cpp", ".c", ".h",
        # JS / TS
        ".js", ".ts", ".mjs",
        # SQL
        ".sql",
        # Config / infra
        ".yaml", ".yml", ".toml", ".cfg", ".ini", ".env",
        # Shell / scripts
        ".sh", ".bash", ".zsh", ".ps1",
        # IaC
        ".tf", ".hcl",
        # Data / serialization
        ".json", ".xml",
    }
    _SKIP_DIRS = {
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", ".idea", "vendor", "target", ".mvn",
        "coverage", ".next", ".nuxt", "out",
    }
    _CONFIG_FILENAMES = {
        "makefile", "dockerfile", "docker-compose.yml", "docker-compose.yaml",
        "requirements.txt", "setup.py", "pyproject.toml", "airflow.cfg",
        ".env.example", "config.yaml", "config.yml",
        "composer.json", "pom.xml", "build.gradle", "package.json",
        "services.yaml", "messenger.yaml", "routing.yaml",
    }
    _CICD_PATH_MARKERS = {
        ".gitlab-ci.yml",
        ".github/workflows/",
        "jenkinsfile",
        ".circleci/",
        "bitbucket-pipelines",
        ".azure-pipelines/",
        ".drone.yml",
    }

    all_file_paths: list[str] = []
    # scored_files: (score, size, path) — lower score = higher priority
    # score 0: keyword/dir match  score 1: any code file  score 2: everything else
    scored_files: list[tuple[int, int, str]] = []
    chosen_ref = ""

    candidate_refs: list[str] = []
    if preferred_branch:
        candidate_refs.append(str(preferred_branch).strip())
    if getattr(repo, "default_branch", None):
        candidate_refs.append(str(repo.default_branch).strip())
    candidate_refs.extend(["main", "master"])

    dedup_refs: list[str] = []
    for ref in candidate_refs:
        if ref and ref not in dedup_refs:
            dedup_refs.append(ref)

    best_tree_items = []
    best_tree_count = -1

    try:
        for ref in dedup_refs:
            try:
                git_tree = repo.get_git_tree(ref, recursive=True)
                blob_count = sum(1 for it in git_tree.tree if getattr(it, "type", None) == "blob")
                if blob_count > best_tree_count:
                    best_tree_count = blob_count
                    best_tree_items = git_tree.tree
                    chosen_ref = ref
            except Exception:
                continue

        if not best_tree_items:
            fallback_ref = dedup_refs[0] if dedup_refs else "main"
            git_tree = repo.get_git_tree(fallback_ref, recursive=True)
            best_tree_items = git_tree.tree
            chosen_ref = fallback_ref

        for item in best_tree_items:
            if item.type != "blob":
                continue
            path = item.path
            path_lower = path.lower()
            filename_lower = path_lower.split("/")[-1]
            ext = ("." + path_lower.rsplit(".", 1)[-1]) if "." in filename_lower else ""
            parts = path_lower.split("/")

            # Skip noise directories
            if any(sd in parts for sd in _SKIP_DIRS):
                continue

            all_file_paths.append(path)

            is_code = ext in _CODE_EXTS
            if not is_code:
                continue

            in_pipeline_dir = any(d in _PIPELINE_DIRS for d in parts[:-1])
            has_keyword = any(kw in path_lower for kw in _PIPELINE_KEYWORDS)
            is_config = filename_lower in _CONFIG_FILENAMES
            is_cicd_file = any(marker in path_lower for marker in _CICD_PATH_MARKERS)
            size = getattr(item, "size", 9999) or 9999

            # Score 0 = runtime pipeline code, 1 = other code, 3 = CI/CD config.
            # CI/CD files are still included as fallback evidence but should not dominate.
            if is_cicd_file:
                score = 3
            elif in_pipeline_dir or has_keyword or is_config:
                score = 0
            else:
                score = 1
            scored_files.append((score, size, path))

    except Exception:
        pass

    # Fetch README from the same ref used for tree traversal.
    readme = ""
    import base64 as _b64
    for candidate in ("README.md", "readme.md"):
        try:
            cf = repo.get_contents(candidate, ref=chosen_ref or None)
            raw = cf.content if cf.encoding == "base64" else None
            if raw:
                readme = _b64.b64decode(raw).decode("utf-8", errors="replace")
            else:
                readme = cf.decoded_content.decode("utf-8", errors="replace")
            if readme:
                break
        except Exception:
            continue

    # Sort: pipeline-relevant first, then by size ascending (smaller = denser info)
    scored_files.sort(key=lambda x: (x[0], x[1]))
    priority_files = [(path, size) for (_, size, path) in scored_files]
    print(f"[Detection] ref:{chosen_ref or 'n/a'} tree:{len(all_file_paths)} code:{len(priority_files)} "
          f"top10={[p for p, _ in priority_files[:10]]}")

    sql_files: list[dict] = []
    python_files: list[dict] = []
    yaml_files: list[dict] = []
    code_files: list[dict] = []   # all other languages (PHP, Java, JS/TS, shell, etc.)

    # Helper: fetch content directly via the already-fetched repo object.
    # This avoids a redundant get_repo() API call per file inside gh.get_file_content().

    def _fetch_content_direct(file_path: str) -> str:
        try:
            cf = repo.get_contents(file_path, ref=chosen_ref or None)
            raw = cf.content if cf.encoding == "base64" else None
            if raw:
                return _b64.b64decode(raw).decode("utf-8", errors="replace")
            return cf.decoded_content.decode("utf-8", errors="replace")
        except Exception:
            return ""

    for file_path, _ in priority_files[:180]:
        try:
            content = _fetch_content_direct(file_path)
            if not content:
                continue
            content = content[:4000]  # 4 KB per file — enough for full PHP Command class
            ext = ("." + file_path.rsplit(".", 1)[-1].lower()) if "." in file_path else ""
            entry = {"path": file_path, "name": file_path.split("/")[-1], "content": content}
            if ext == ".sql":
                sql_files.append(entry)
            elif ext == ".py":
                python_files.append(entry)
            elif ext in (".yaml", ".yml", ".toml", ".cfg", ".ini"):
                yaml_files.append(entry)
            else:
                code_files.append(entry)
        except Exception:
            pass

    return {
        "repo_name": repo_name,
        "owner": owner,
        "description": repo.description or "",
        "languages": languages,
        "topics": topics,
        "readme": readme[:6000],
        "structure": {"files": [{"path": p} for p in all_file_paths[:500]]},
        "sql_files": sql_files,
        "python_files": python_files,
        "yaml_files": yaml_files,
        "code_files": code_files,
        "json_files": [],
        "notebook_files": [],
    }


@router.post("/projects/{project_id}/pipeline/detect-pipelines")
async def pipeline_step_detect_pipelines(project_id: str):
    """
    Detect distinct data pipelines / flux / modules from all connected
    sources of a project.  Returns a structured list the user can select from.
    """
    p = _projects.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    # Fast source summary to keep UI responsive
    source_content = _get_source_content_for_project(project_id, lightweight=True)
    datasource_context = _build_quick_datasource_context(project_id)

    # Build lightweight metadata for GitHub sources (avoid deep crawling)
    metadata_list = []
    for src in p.get("sources", []):
        cfg = src.get("config", {})
        if src.get("type") == "github" and connections.get("github"):
            owner = cfg.get("owner", "")
            repo = cfg.get("repo", "")
            branch = cfg.get("branch", "")
            if owner and repo:
                try:
                    meta = _get_repo_metadata_lightweight(owner, repo, branch)
                    if meta:
                        metadata_list.append(meta)
                except Exception:
                    pass

    if metadata_list:
        metadata = _merge_repo_metadata(metadata_list)
    else:
        metadata = {
            "repo_name": p["name"],
            "owner": "",
            "description": p.get("description", ""),
            "readme": source_content,
            "languages": "",
            "topics": "",
            "structure": {},
            "sql_files": [],
            "python_files": [],
            "yaml_files": [],
            "json_files": [],
            "notebook_files": [],
        }

    if datasource_context:
        metadata["datasource_context"] = datasource_context
    if source_content and not metadata_list:
        metadata["readme"] = source_content

    py_count = len(metadata.get("python_files", []))
    sql_count = len(metadata.get("sql_files", []))
    yaml_count = len(metadata.get("yaml_files", []))
    code_count = len(metadata.get("code_files", []))
    file_count = len(metadata.get("structure", {}).get("files", []))
    logger.info(
        "Pipeline detection for project %s — files:%d py:%d sql:%d yaml:%d code(php/java/js):%d ctx_len:%d",
        project_id, file_count, py_count, sql_count, yaml_count, code_count,
        len(metadata.get("datasource_context", "")),
    )

    agent = PipelineDetectionAgent()
    try:
        # Bound LLM latency so frontend never spins forever.
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(agent.detect, metadata)
            result = future.result(timeout=90)
    except FuturesTimeoutError:
        result = {
            "pipelines": [
                {
                    "id": "default_pipeline",
                    "name": "Default Project Pipeline",
                    "description": "Detection timed out. Using a default pipeline so you can continue.",
                    "type": "other",
                    "confidence": 0.3,
                    "explainability": {
                        "keywords": [],
                        "orchestration_clues": [],
                        "evidence_files": [],
                        "evidence_tables": [],
                    },
                    "source_files": [],
                    "source_tables": [],
                    "technologies": [],
                }
            ],
            "count": 1,
            "summary": "Detection timed out; fallback pipeline returned.",
        }
    except Exception as exc:
        logger.exception("Pipeline detection failed for project %s: %s", project_id, exc)
        result = {
            "pipelines": [
                {
                    "id": "default_pipeline",
                    "name": "Default Project Pipeline",
                    "description": "Detection failed unexpectedly. Using a default pipeline so you can continue.",
                    "type": "other",
                    "confidence": 0.3,
                    "explainability": {
                        "keywords": [],
                        "orchestration_clues": [],
                        "evidence_files": [],
                        "evidence_tables": [],
                    },
                    "source_files": [],
                    "source_tables": [],
                    "technologies": [],
                }
            ],
            "count": 1,
            "summary": "Detection failed; fallback pipeline returned.",
        }

    # Persist detected pipelines in pipeline state
    normalized_pipelines = [
        _normalize_detected_pipeline(p, i + 1)
        for i, p in enumerate(result.get("pipelines", []))
    ]
    filtered_pipelines, removed_cicd = _filter_cicd_only_pipelines(normalized_pipelines)
    if removed_cicd:
        logger.info(
            "Filtered %d CI/CD-only pipelines for project %s (kept %d real code/data pipelines)",
            removed_cicd,
            project_id,
            len(filtered_pipelines),
        )

    result["pipelines"] = filtered_pipelines
    result["count"] = len(filtered_pipelines)

    _pipeline_state.setdefault(project_id, {})
    _pipeline_state[project_id]["detected_pipelines"] = filtered_pipelines
    _pipeline_state[project_id]["original_detected_pipelines"] = [
        dict(p) for p in filtered_pipelines
    ]
    if filtered_pipelines and not _pipeline_state[project_id].get("selected_pipeline"):
        _pipeline_state[project_id]["selected_pipeline"] = filtered_pipelines[0]

    _persist_state()
    return result


@router.post("/projects/{project_id}/pipeline/select")
async def pipeline_select(project_id: str, req: PipelineSelectRequest):
    """Persist the selected pipeline for downstream extraction/mapping context."""
    state = _pipeline_state.setdefault(project_id, {})
    pipelines = state.get("detected_pipelines", [])
    selected = next((p for p in pipelines if p.get("id") == req.pipeline_id), None)
    if not selected:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    state["selected_pipeline"] = selected
    _persist_state()
    return {"selected_pipeline": selected}


@router.post("/projects/{project_id}/pipeline/reset-pipelines")
async def pipeline_reset_pipelines(project_id: str):
    """Restore pipelines to the original detection result captured on first load."""
    state = _pipeline_state.get(project_id)
    if not state:
        raise HTTPException(status_code=404, detail="Pipeline state not found")

    original = state.get("original_detected_pipelines") or []
    if not original:
        raise HTTPException(status_code=400, detail="No original detected pipelines available")

    restored = [_normalize_detected_pipeline(p, i + 1) for i, p in enumerate(original)]
    state["detected_pipelines"] = restored
    state["selected_pipeline"] = restored[0] if restored else None

    return {
        "pipelines": restored,
        "selected_pipeline": state.get("selected_pipeline"),
    }


@router.post("/projects/{project_id}/pipeline/update-pipelines")
async def pipeline_update_pipelines(project_id: str, req: PipelineUpdateRequest):
    """Save user-edited pipelines (rename/reorder/manual edits)."""
    if not isinstance(req.pipelines, list) or len(req.pipelines) == 0:
        raise HTTPException(status_code=400, detail="pipelines must be a non-empty list")
    state = _pipeline_state.setdefault(project_id, {})
    normalized = [_normalize_detected_pipeline(p, i + 1) for i, p in enumerate(req.pipelines)]
    state["detected_pipelines"] = normalized

    selected = state.get("selected_pipeline")
    if selected:
        selected_id = selected.get("id")
        state["selected_pipeline"] = next(
            (p for p in normalized if p.get("id") == selected_id),
            normalized[0],
        )
    else:
        state["selected_pipeline"] = normalized[0]

    _persist_state()
    return {
        "pipelines": normalized,
        "selected_pipeline": state.get("selected_pipeline"),
    }


@router.post("/projects/{project_id}/pipeline/split")
async def pipeline_split(project_id: str, req: PipelineSplitRequest):
    """Split one pipeline into two editable child pipelines."""
    state = _pipeline_state.setdefault(project_id, {})
    pipelines = state.get("detected_pipelines", [])
    target_idx = next((i for i, p in enumerate(pipelines) if p.get("id") == req.pipeline_id), None)
    if target_idx is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    target = pipelines[target_idx]
    name_1 = req.split_name_1.strip()
    name_2 = req.split_name_2.strip()
    if not name_1 or not name_2:
        raise HTTPException(status_code=400, detail="Split names are required")

    base_files = target.get("source_files") or []
    half = max(1, len(base_files) // 2) if base_files else 0
    files_1 = base_files[:half] if half else []
    files_2 = base_files[half:] if half else []
    if base_files and not files_2:
        files_2 = [base_files[-1]]

    base_tables = target.get("source_tables") or []
    thalf = max(1, len(base_tables) // 2) if base_tables else 0
    tables_1 = base_tables[:thalf] if thalf else []
    tables_2 = base_tables[thalf:] if thalf else []
    if base_tables and not tables_2:
        tables_2 = [base_tables[-1]]

    explain = target.get("explainability") or {}
    p1 = _normalize_detected_pipeline({
        **target,
        "id": f"{target.get('id')}_a",
        "name": name_1,
        "description": (target.get("description") or "") + " (split A)",
        "source_files": files_1,
        "source_tables": tables_1,
        "confidence": min(0.99, max(0.2, float(target.get("confidence", 0.5)) - 0.1)),
        "explainability": {
            "keywords": explain.get("keywords") or [],
            "orchestration_clues": explain.get("orchestration_clues") or [],
            "evidence_files": files_1[:5],
            "evidence_tables": tables_1[:5],
        },
    }, target_idx + 1)
    p2 = _normalize_detected_pipeline({
        **target,
        "id": f"{target.get('id')}_b",
        "name": name_2,
        "description": (target.get("description") or "") + " (split B)",
        "source_files": files_2,
        "source_tables": tables_2,
        "confidence": min(0.99, max(0.2, float(target.get("confidence", 0.5)) - 0.1)),
        "explainability": {
            "keywords": explain.get("keywords") or [],
            "orchestration_clues": explain.get("orchestration_clues") or [],
            "evidence_files": files_2[:5],
            "evidence_tables": tables_2[:5],
        },
    }, target_idx + 2)

    new_pipelines = pipelines[:target_idx] + [p1, p2] + pipelines[target_idx + 1:]
    state["detected_pipelines"] = new_pipelines
    state["selected_pipeline"] = p1
    _persist_state()
    return {"pipelines": new_pipelines, "selected_pipeline": p1}


@router.post("/projects/{project_id}/pipeline/merge")
async def pipeline_merge(project_id: str, req: PipelineMergeRequest):
    """Merge selected pipelines into a single pipeline."""
    state = _pipeline_state.setdefault(project_id, {})
    pipelines = state.get("detected_pipelines", [])
    merge_ids = [str(pid) for pid in req.pipeline_ids if pid]
    if len(merge_ids) < 2:
        raise HTTPException(status_code=400, detail="At least two pipelines are required for merge")

    selected = [p for p in pipelines if p.get("id") in merge_ids]
    if len(selected) < 2:
        raise HTTPException(status_code=404, detail="Could not find requested pipelines")

    merged_name = req.merged_name.strip()
    if not merged_name:
        raise HTTPException(status_code=400, detail="merged_name is required")

    merged = {
        "id": "merged_" + _new_id(),
        "name": merged_name,
        "description": "Merged pipeline from: " + ", ".join(p.get("name", p.get("id", "")) for p in selected),
        "type": selected[0].get("type", "other"),
        "execution_mode": selected[0].get("execution_mode", "batch"),
        "launcher": selected[0].get("launcher", "unknown"),
        "confidence": max(0.1, sum(float(p.get("confidence", 0.5)) for p in selected) / len(selected) - 0.05),
        "triggers": [t for p in selected for t in (p.get("triggers") or [])],
        "listen_mode": [lm for p in selected for lm in (p.get("listen_mode") or [])],
        "queues": list({q["name"]: q for p in selected for q in (p.get("queues") or [])}.values()),
        "jobs": [j for p in selected for j in (p.get("jobs") or [])],
        "sub_pipelines": list({sp for p in selected for sp in (p.get("sub_pipelines") or [])}),
        "parent_pipeline": selected[0].get("parent_pipeline"),
        "source_files": list({f for p in selected for f in (p.get("source_files") or [])}),
        "source_tables": list({t for p in selected for t in (p.get("source_tables") or [])}),
        "technologies": list({t for p in selected for t in (p.get("technologies") or [])}),
        "explainability": {
            "keywords": list({k for p in selected for k in ((p.get("explainability") or {}).get("keywords") or [])}),
            "orchestration_clues": list({c for p in selected for c in ((p.get("explainability") or {}).get("orchestration_clues") or [])}),
            "evidence_files": list({f for p in selected for f in ((p.get("explainability") or {}).get("evidence_files") or [])})[:10],
            "evidence_tables": list({t for p in selected for t in ((p.get("explainability") or {}).get("evidence_tables") or [])})[:10],
        },
    }
    merged = _normalize_detected_pipeline(merged, 1)

    remaining = [p for p in pipelines if p.get("id") not in merge_ids]
    remaining.append(merged)
    state["detected_pipelines"] = remaining
    state["selected_pipeline"] = merged
    _persist_state()
    return {"pipelines": remaining, "selected_pipeline": merged}


@router.post("/projects/{project_id}/pipeline/reorder")
async def pipeline_reorder(project_id: str, req: PipelineReorderRequest):
    """Reorder pipelines based on user-defined pipeline IDs order."""
    state = _pipeline_state.setdefault(project_id, {})
    pipelines = state.get("detected_pipelines", [])
    id_to_pipeline = {p.get("id"): p for p in pipelines}
    reordered = [id_to_pipeline[pid] for pid in req.pipeline_ids if pid in id_to_pipeline]
    leftovers = [p for p in pipelines if p.get("id") not in req.pipeline_ids]
    new_pipelines = reordered + leftovers
    if not new_pipelines:
        raise HTTPException(status_code=400, detail="No valid pipeline IDs for reorder")

    state["detected_pipelines"] = new_pipelines
    if state.get("selected_pipeline"):
        sid = state["selected_pipeline"].get("id")
        state["selected_pipeline"] = next((p for p in new_pipelines if p.get("id") == sid), new_pipelines[0])
    else:
        state["selected_pipeline"] = new_pipelines[0]
    _persist_state()
    return {"pipelines": new_pipelines, "selected_pipeline": state.get("selected_pipeline")}


@router.post("/projects/{project_id}/pipeline/template")
async def pipeline_step_template(
    project_id: str,
    template_file: UploadFile = File(...),
):
    """Step 1: Parse template, extract placeholders using TemplateAgent."""
    p = _projects.get(project_id)
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

    # Preserve detection state while updating template-related state
    state = _pipeline_state.setdefault(project_id, {})
    state.update({
        "step": "template",
        "template_text": template_text,
        "template_title": detected.get("template_title", ""),
        "sections": detected.get("sections", []),
        "placeholders": fields,
        "values": {},
        "spec": "",
        "validation": None,
    })

    return {
        "template_title": detected.get("template_title", ""),
        "sections": detected.get("sections", []),
        "placeholders": fields,
    }


@router.post("/projects/{project_id}/pipeline/extract")
async def pipeline_step_extract(project_id: str, req: PipelineConfirmPlaceholdersRequest):
    """Step 2: With confirmed placeholders, extract values from all connected sources."""
    p = _projects.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    state = _pipeline_state.get(project_id)
    if not state:
        raise HTTPException(status_code=400, detail="Run template step first.")

    # Save confirmed placeholders
    state["placeholders"] = req.placeholders
    state["step"] = "extract"

    # Gather source content as a pseudo-metadata dict
    source_content = _get_source_content_for_project(project_id)

    # Build live data source schema context from all connected sources
    datasource_context = _build_datasource_context()

    metadata = {
        "repo_name": p["name"],
        "owner": "",
        "description": p.get("description", ""),
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

    selected_pipeline = state.get("selected_pipeline")
    if selected_pipeline:
        metadata["selected_pipeline"] = selected_pipeline
        metadata["description"] = (
            f"{metadata['description']}\n\nSelected pipeline: {selected_pipeline.get('name', '')}"
            f"\nType: {selected_pipeline.get('type', '')}"
            f"\nDescription: {selected_pipeline.get('description', '')}"
        ).strip()

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

        source_label = "Sources"
        for src in p.get("sources", []):
            source_label = src.get("label", src.get("type", "Source"))
            break  # just first source for now

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
async def pipeline_step_map(project_id: str, req: PipelineConfirmValuesRequest):
    """Step 3: With confirmed values, compose the final spec via MappingAgent."""
    p = _projects.get(project_id)
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
    version = _create_spec_version(project_id, state, spec, validation)
    _persist_state()

    return {
        "spec": spec,
        "validation": validation,
        "version": {
            "id": version["id"],
            "version_number": version["version_number"],
            "status": version["status"],
            "created_at": version["created_at"],
        },
    }


@router.post("/projects/{project_id}/pipeline/export")
async def pipeline_step_export(project_id: str, req: ExportRequest):
    """Step 4: Return the finalized spec in the requested format."""
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
                "versions": [
                    {
                        "id": v.get("id"),
                        "version_number": v.get("version_number"),
                        "status": v.get("status"),
                        "created_at": v.get("created_at"),
                    }
                    for v in state.get("spec_versions", [])
                ],
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
        "detected_pipelines": state.get("detected_pipelines", []),
        "selected_pipeline": state.get("selected_pipeline"),
        "template_title": state.get("template_title", ""),
        "placeholders": state.get("placeholders", []),
        "extraction_results": state.get("extraction_results", []),
        "values": state.get("values", {}),
        "spec": state.get("spec", ""),
        "validation": state.get("validation"),
        "spec_versions": [
            {
                "id": v.get("id"),
                "version_number": v.get("version_number"),
                "status": v.get("status"),
                "created_at": v.get("created_at"),
            }
            for v in state.get("spec_versions", [])
        ],
    }


@router.get("/projects/{project_id}/pipeline/spec-versions")
async def pipeline_get_spec_versions(project_id: str):
    state = _pipeline_state.get(project_id)
    if not state:
        return {"versions": [], "approved_version_id": None}
    versions = state.get("spec_versions", [])
    return {
        "versions": [
            {
                "id": v.get("id"),
                "version_number": v.get("version_number"),
                "status": v.get("status"),
                "created_at": v.get("created_at"),
                "validation": v.get("validation"),
                "spec": v.get("spec", ""),
            }
            for v in versions
        ],
        "approved_version_id": state.get("approved_version_id"),
    }


@router.post("/projects/{project_id}/pipeline/spec-versions/diff")
async def pipeline_diff_spec_versions(project_id: str, req: PipelineVersionDiffRequest):
    state = _pipeline_state.get(project_id)
    if not state:
        raise HTTPException(status_code=404, detail="Pipeline state not found")

    versions = state.get("spec_versions", [])
    from_version = next((v for v in versions if v.get("id") == req.from_version_id), None)
    to_version = next((v for v in versions if v.get("id") == req.to_version_id), None)
    if not from_version or not to_version:
        raise HTTPException(status_code=404, detail="Version not found")

    from_lines = (from_version.get("spec") or "").splitlines()
    to_lines = (to_version.get("spec") or "").splitlines()
    diff_lines = list(difflib.unified_diff(from_lines, to_lines, fromfile="from", tofile="to", lineterm=""))

    return {
        "from_version_id": req.from_version_id,
        "to_version_id": req.to_version_id,
        "diff": "\n".join(diff_lines),
        "from_spec": from_version.get("spec", ""),
        "to_spec": to_version.get("spec", ""),
    }


@router.post("/projects/{project_id}/pipeline/spec-versions/{version_id}/promote")
async def pipeline_promote_spec_version(project_id: str, version_id: str):
    state = _pipeline_state.get(project_id)
    if not state:
        raise HTTPException(status_code=404, detail="Pipeline state not found")

    versions = state.get("spec_versions", [])
    target = next((v for v in versions if v.get("id") == version_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Version not found")

    for v in versions:
        if v.get("id") == version_id:
            v["status"] = "approved"
        elif v.get("status") == "approved":
            v["status"] = "draft"

    state["approved_version_id"] = version_id

    # Persist approved spec into the project object so it survives wizard navigation
    p = _projects.get(project_id)
    if p is not None:
        approved_specs = p.setdefault("approved_specs", [])
        # Replace any existing entry for this version_id; otherwise append
        existing = next((s for s in approved_specs if s.get("version_id") == version_id), None)
        selected_pipeline = state.get("selected_pipeline") or {}
        entry = {
            "version_id": version_id,
            "version_number": target.get("version_number"),
            "spec": target.get("spec", ""),
            "approved_at": _now(),
            "pipeline_name": selected_pipeline.get("name", "N/A"),
            "pipeline_id": selected_pipeline.get("id", ""),
        }
        if existing:
            existing.update(entry)
        else:
            approved_specs.append(entry)

    return {
        "approved_version_id": version_id,
        "version": {
            "id": target.get("id"),
            "version_number": target.get("version_number"),
            "status": target.get("status"),
            "created_at": target.get("created_at"),
        },
    }


@router.get("/projects/{project_id}/approved-specs")
async def get_project_approved_specs(project_id: str):
    """Return all specs that have been promoted to approved for this project."""
    p = _projects.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"approved_specs": p.get("approved_specs", [])}


@router.post("/projects/{project_id}/chat")
async def project_chat(project_id: str, req: ProjectChatRequest):
    """Project-aware chat powered by gpt-4o-mini with full context injection."""
    p = _projects.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    state = _pipeline_state.get(project_id, {})

    # Gather source snippets
    source_lines = []
    for src in p.get("sources", []):
        cfg = src.get("config", {})
        source_lines.append(f"- {src.get('label', '')} ({src.get('type', '')}) config={json.dumps(cfg)[:200]}")
    sources_text = "\n".join(source_lines) if source_lines else "No sources connected."

    # Build live data source context (real schemas, tables, files from connected sources)
    live_datasource_context = _build_datasource_context()

    # Build system prompt with full pipeline context
    system_parts = [
        "You are a helpful data engineering assistant for a spec-generation platform called Jems Spec Generator.",
        "You have access to the real schemas, tables, and content of the connected data sources listed below.",
        "Use this information to answer questions precisely — reference actual table names, column names, and data structures when relevant.",
        f"Current project: {p['name']}",
        f"Project description: {p.get('description', 'N/A')}",
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
async def list_projects():
    """List all projects (newest first)"""
    items = sorted(_projects.values(), key=lambda p: p["created_at"], reverse=True)
    return {"projects": items}


@router.post("/projects")
async def create_project(req: CreateProjectRequest):
    """Create a new project"""
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")
    pid = _new_id()
    project = {
        "id": pid,
        "name": name,
        "description": req.description.strip(),
        "sources": [],
        "created_at": _now(),
    }
    _projects[pid] = project
    _persist_state()
    return project


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    """Get a single project by ID"""
    p = _projects.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@router.put("/projects/{project_id}")
async def update_project(project_id: str, req: UpdateProjectRequest):
    """Update project name/description"""
    p = _projects.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    if req.name is not None:
        p["name"] = req.name.strip()
    if req.description is not None:
        p["description"] = req.description.strip()
    _persist_state()
    return p


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project"""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="Project not found")
    del _projects[project_id]
    _pipeline_state.pop(project_id, None)
    _persist_state()
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
async def add_source(project_id: str, req: AddSourceRequest):
    """Add a source to a project"""
    p = _projects.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    stype = req.type.lower()
    if stype not in SOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown source type: {stype}")

    meta = SOURCE_TYPES[stype]
    source = {
        "id": _new_id(),
        "type": stype,
        "type_name": meta["name"],
        "icon": meta["icon"],
        "label": req.label.strip() or meta["name"],
        "config": req.config,
        "status": "connected",
        "added_at": _now(),
    }
    p["sources"].append(source)
    _persist_state()
    return source


@router.delete("/projects/{project_id}/sources/{source_id}")
async def remove_source(project_id: str, source_id: str):
    """Remove a source from a project"""
    p = _projects.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    before = len(p["sources"])
    p["sources"] = [s for s in p["sources"] if s["id"] != source_id]
    if len(p["sources"]) == before:
        raise HTTPException(status_code=404, detail="Source not found")
    _persist_state()
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
