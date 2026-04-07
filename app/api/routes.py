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

# ============== IN-MEMORY PROJECT STORE ==============
import uuid as _uuid
from datetime import datetime as _dt

_projects = {}  # id -> project dict


def _new_id():
    return _uuid.uuid4().hex[:12]


def _now():
    return _dt.utcnow().isoformat() + "Z"


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


def _get_source_content_for_project(project_id: str) -> str:
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

    return {
        "spec": spec,
        "validation": validation,
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

    # Build system prompt with full pipeline context
    system_parts = [
        "You are a helpful assistant for a spec-generation platform.",
        f"Current project: {p['name']}",
        f"Project description: {p.get('description', 'N/A')}",
        f"Connected sources:\n{sources_text}",
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
    return p


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project"""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="Project not found")
    del _projects[project_id]
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
