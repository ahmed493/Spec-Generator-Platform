import sys
import json
from app.db import SessionLocal
from app.models import Project
from app.agents.extraction_agent import ExtractionAgent
from app.agents.llm_client import get_llm_client
from app.mcp_servers.github_server import GitHubMCPServer
from app.config.settings import settings

# Get demo-app project
db = SessionLocal()
p = db.query(Project).filter(Project.name == 'demo-app').first()
db.close()

if not p:
    print("demo-app project not found")
    sys.exit(1)

# Get GitHub connection from state (need to initialize it)
print("Initializing GitHub connection...")
try:
    if not settings.github_token:
        print("ERROR: No GitHub token in settings (.env file)")
        sys.exit(1)
    github_mcp = GitHubMCPServer(token=settings.github_token)
    print(f"GitHub connected as: {github_mcp.token[:20]}..." if github_mcp.token else "No GitHub token")
except Exception as e:
    print(f"GitHub init failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Prepare metadata
metadata = {
    "repo_name": "demo-app",
    "owner": "ahmed493",
    "description": "",
    "readme": "",
    "languages": "",
    "topics": "",
    "python_files": [],
    "sql_files": [],
    "yaml_files": [],
    "code_files": [],
}

# Test with a few placeholder fields
placeholders = [
    {"id": "source", "label": "Source"},
    {"id": "destination", "label": "Destination"},
    {"id": "frequency", "label": "Frequency"},
]

print("\nTesting extraction...")
print(f"Repository: {metadata['owner']}/{metadata['repo_name']}")
print(f"Fields to extract: {[p['label'] for p in placeholders]}\n")

try:
    agent = ExtractionAgent(mcp_client=github_mcp)
    extracted = agent.extract(metadata, placeholders)
    
    print("Extraction results:")
    for field in placeholders:
        field_id = field['id']
        value = extracted.get(field_id, "")
        is_not_found = (
            not value or 
            value.strip().lower() in {'not_found', 'not found', 'non trouvé', 'non identifié', 'n/a', ''}
        )
        print(f"  {field['label']:20} => {value[:50] if value else '(empty)':50} {'[NOT_FOUND]' if is_not_found else '[FOUND]'}")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
