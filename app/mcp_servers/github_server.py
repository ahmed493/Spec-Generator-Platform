"""
MCP Server for GitHub
Extracts code, structure, and metadata from GitHub repositories
"""
import logging
import time
import requests
from github import Github, Repository
from typing import Optional
import base64
import json

logger = logging.getLogger(__name__)


class GitHubMCPServer:
    """MCP Server to connect and extract data from GitHub repositories"""
    
    def __init__(self, token: str):
        self.token = token
        self.client: Optional[Github] = None
        self.connected = False
    
    def connect(self) -> bool:
        """Connect to GitHub using the provided token"""
        try:
            self.client = Github(self.token)
            # Test connection by getting user
            user = self.client.get_user()
            logger.info("Connected to GitHub as: %s", user.login)
            self.connected = True
            return True
        except Exception as e:
            logger.error("Failed to connect to GitHub: %s", e)
            self.connected = False
            return False
    
    def get_repo(self, owner: str, repo_name: str) -> Optional[Repository.Repository]:
        """Get a specific repository"""
        if not self.connected:
            raise Exception("Not connected to GitHub")
        try:
            return self.client.get_repo(f"{owner}/{repo_name}")
        except Exception as e:
            logger.error("Failed to get repo %s/%s: %s", owner, repo_name, e)
            return None
    
    def get_repo_structure(self, owner: str, repo_name: str, path: str = "") -> dict:
        """Get the file/folder structure of a repository"""
        repo = self.get_repo(owner, repo_name)
        if not repo:
            return {}
        
        structure = {
            "name": repo_name,
            "description": repo.description,
            "default_branch": repo.default_branch,
            "languages": dict(repo.get_languages()),
            "files": []
        }
        
        try:
            contents = repo.get_contents(path)
            for content in contents:
                item = {
                    "name": content.name,
                    "path": content.path,
                    "type": content.type,  # "file" or "dir"
                    "size": content.size if content.type == "file" else None
                }
                structure["files"].append(item)
                
                # Recursively get subdirectories (limit depth to 2)
                if content.type == "dir" and path.count("/") < 2:
                    sub_contents = self.get_repo_structure(owner, repo_name, content.path)
                    item["children"] = sub_contents.get("files", [])
        except Exception as e:
            logger.warning("Error getting contents: %s", e)
        
        return structure
    
    def get_file_content(self, owner: str, repo_name: str, file_path: str) -> Optional[str]:
        """Get the content of a specific file"""
        repo = self.get_repo(owner, repo_name)
        if not repo:
            return None
        
        try:
            content = repo.get_contents(file_path)
            if content.encoding == "base64":
                return base64.b64decode(content.content).decode("utf-8")
            return content.decoded_content.decode("utf-8")
        except Exception as e:
            logger.error("Failed to get file %s: %s", file_path, e)
            return None

    def fetch_files_by_paths(
        self,
        owner: str,
        repo_name: str,
        paths: list[str],
        branch: Optional[str] = None,
        max_chars: int = 8000,
    ) -> list[dict]:
        """Fetch the content of specific file paths via the REST API (no PyGitHub quota overhead).

        Useful for targeted top-up: ensure pipeline evidence files are always in the
        extraction context even when the general fetcher's category caps excluded them.

        Returns:
            List of {"path": str, "content": str} — only for paths that were
            successfully fetched (missing or binary files are silently skipped).
        """
        if not paths:
            return []

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        base = "https://api.github.com"

        # Resolve default branch once if not provided
        if not branch:
            try:
                r = requests.get(
                    f"{base}/repos/{owner}/{repo_name}",
                    headers=headers, timeout=10,
                )
                r.raise_for_status()
                branch = r.json().get("default_branch", "main")
            except Exception as exc:
                logger.warning("[fetch_files_by_paths] Could not resolve branch: %s", exc)
                branch = "main"

        results: list[dict] = []
        for path in paths:
            try:
                time.sleep(0.05)
                r = requests.get(
                    f"{base}/repos/{owner}/{repo_name}/contents/{path}",
                    headers=headers,
                    params={"ref": branch},
                    timeout=15,
                )
                if r.status_code == 404:
                    logger.debug("[fetch_files_by_paths] Not found: %s", path)
                    continue
                r.raise_for_status()
                data = r.json()
                raw = data.get("content", "")
                if data.get("encoding") == "base64":
                    try:
                        content = base64.b64decode(raw.replace("\n", "")).decode("utf-8", errors="replace")
                    except Exception:
                        continue
                else:
                    content = raw
                results.append({"path": path, "content": content[:max_chars]})
            except Exception as exc:
                logger.warning("[fetch_files_by_paths] Failed %s: %s", path, exc)

        logger.info(
            "[fetch_files_by_paths] %s/%s — requested:%d fetched:%d",
            owner, repo_name, len(paths), len(results),
        )
        return results

    def search_code_in_repo(
        self,
        owner: str,
        repo_name: str,
        query: str,
        max_results: int = 10,
    ) -> list[dict]:
        """Search for code matching *query* inside a specific repository using
        the GitHub code-search API.  Returns a list of matching files with their
        path and a short content snippet (first 3000 chars of actual file).

        Useful for Pass-2 retries: instead of re-scanning the same cached files,
        search for files that actually contain the keyword/table-name being sought.
        """
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        base = "https://api.github.com"
        full_query = f"{query} repo:{owner}/{repo_name}"

        try:
            r = requests.get(
                f"{base}/search/code",
                headers=headers,
                params={"q": full_query, "per_page": min(max_results, 30)},
                timeout=20,
            )
            r.raise_for_status()
            items = r.json().get("items", [])
        except Exception as exc:
            logger.warning("[search_code_in_repo] Search failed for '%s': %s", query, exc)
            return []

        results: list[dict] = []
        for item in items[:max_results]:
            path = item.get("path", "")
            content = self.get_file_content(owner, repo_name, path) or ""
            results.append({"path": path, "content": content[:3000]})
            time.sleep(0.1)  # respect secondary rate limits

        logger.info(
            "[search_code_in_repo] '%s' in %s/%s → %d matches",
            query, owner, repo_name, len(results),
        )
        return results

    def get_sql_files(self, owner: str, repo_name: str) -> list[dict]:
        """Find and extract all SQL files from a repository"""
        sql_files = []
        repo = self.get_repo(owner, repo_name)
        if not repo:
            return sql_files
        
        def search_sql(path: str = ""):
            try:
                contents = repo.get_contents(path)
                for content in contents:
                    if content.type == "dir":
                        search_sql(content.path)
                    elif content.name.endswith(".sql"):
                        file_content = self.get_file_content(owner, repo_name, content.path)
                        sql_files.append({
                            "path": content.path,
                            "name": content.name,
                            "content": file_content
                        })
            except Exception:
                pass
        
        search_sql()
        return sql_files
    
    def get_python_files(self, owner: str, repo_name: str) -> list[dict]:
        """Find and extract all Python files from a repository"""
        py_files = []
        repo = self.get_repo(owner, repo_name)
        if not repo:
            return py_files
        
        def search_py(path: str = ""):
            try:
                contents = repo.get_contents(path)
                for content in contents:
                    if content.type == "dir":
                        search_py(content.path)
                    elif content.name.endswith(".py"):
                        file_content = self.get_file_content(owner, repo_name, content.path)
                        py_files.append({
                            "path": content.path,
                            "name": content.name,
                            "content": file_content
                        })
            except Exception:
                pass
        
        search_py()
        return py_files

    def get_yaml_files(self, owner: str, repo_name: str) -> list[dict]:
        """Find and extract all YAML/YML and config files from a repository"""
        yaml_files = []
        repo = self.get_repo(owner, repo_name)
        if not repo:
            return yaml_files
        
        def search_yaml(path: str = ""):
            try:
                contents = repo.get_contents(path)
                for content in contents:
                    if content.type == "dir":
                        search_yaml(content.path)
                    elif content.name.endswith((".yaml", ".yml", ".toml", ".cfg", ".ini")):
                        file_content = self.get_file_content(owner, repo_name, content.path)
                        yaml_files.append({
                            "path": content.path,
                            "name": content.name,
                            "content": file_content
                        })
            except Exception:
                pass
        
        search_yaml()
        return yaml_files

    def get_json_files(self, owner: str, repo_name: str) -> list[dict]:
        """Find and extract JSON files from a repository (skip package-lock and node_modules)"""
        json_files = []
        repo = self.get_repo(owner, repo_name)
        if not repo:
            return json_files
        
        _skip_names = {"package-lock.json", "yarn.lock"}
        _skip_dirs = {"node_modules", ".git", "__pycache__", ".venv", "venv"}
        
        def search_json(path: str = ""):
            try:
                contents = repo.get_contents(path)
                for content in contents:
                    if content.type == "dir":
                        if content.name not in _skip_dirs:
                            search_json(content.path)
                    elif content.name.endswith(".json") and content.name not in _skip_names:
                        file_content = self.get_file_content(owner, repo_name, content.path)
                        json_files.append({
                            "path": content.path,
                            "name": content.name,
                            "content": file_content
                        })
            except Exception:
                pass
        
        search_json()
        return json_files

    def get_notebook_files(self, owner: str, repo_name: str) -> list[dict]:
        """Find and extract Jupyter notebook files (.ipynb) from a repository"""
        nb_files = []
        repo = self.get_repo(owner, repo_name)
        if not repo:
            return nb_files
        
        def search_nb(path: str = ""):
            try:
                contents = repo.get_contents(path)
                for content in contents:
                    if content.type == "dir":
                        search_nb(content.path)
                    elif content.name.endswith(".ipynb"):
                        file_content = self.get_file_content(owner, repo_name, content.path)
                        # Extract only source cells, skip output/metadata
                        try:
                            nb_json = json.loads(file_content or "{}")
                            cells = nb_json.get("cells", [])
                            sources = []
                            for cell in cells:
                                if cell.get("cell_type") in ("code", "markdown"):
                                    src = "".join(cell.get("source", []))
                                    if src.strip():
                                        sources.append(f"[{cell['cell_type']}]\n{src}")
                            readable = "\n\n".join(sources)
                        except Exception:
                            readable = file_content or ""
                        nb_files.append({
                            "path": content.path,
                            "name": content.name,
                            "content": readable
                        })
            except Exception:
                pass
        
        search_nb()
        return nb_files

    def get_repo_metadata(self, owner: str, repo_name: str) -> dict:
        """Get comprehensive metadata about a repository using the efficient git-tree API.

        Uses a single recursive git-tree call to list all files, then fetches
        individual blobs — same approach as github_file_fetcher.fetch_repo_files
        but returning the same dict shape as the old implementation so all
        existing callers continue to work unchanged.
        """
        repo = self.get_repo(owner, repo_name)
        if not repo:
            return {}

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        base_url = "https://api.github.com"
        branch = repo.default_branch or "main"

        # ── 1. Fetch full recursive git tree (1 API call) ────────────────────
        try:
            r = requests.get(
                f"{base_url}/repos/{owner}/{repo_name}/git/trees/{branch}",
                headers=headers,
                params={"recursive": "1"},
                timeout=30,
            )
            r.raise_for_status()
            tree_items = r.json().get("tree", [])
        except Exception as exc:
            logger.error("[get_repo_metadata] git-tree fetch failed: %s", exc)
            tree_items = []

        _SKIP_DIRS = {
            "node_modules", ".git", "__pycache__", ".venv", "venv",
            "dist", "build", ".idea", "vendor", "target",
        }
        _EXT_TO_CAT = {
            ".py": "python_files", ".sql": "sql_files",
            ".yaml": "yaml_files", ".yml": "yaml_files",
            ".toml": "yaml_files", ".cfg": "yaml_files", ".ini": "yaml_files",
            ".json": "json_files", ".ipynb": "notebook_files",
        }
        _CAPS = {
            "python_files": 20, "sql_files": 15, "yaml_files": 15,
            "json_files": 10, "notebook_files": 5,
        }
        _SKIP_NAMES = {"package-lock.json", "yarn.lock"}
        _MAX_CHARS = 4000

        buckets: dict[str, list[dict]] = {k: [] for k in _CAPS}
        readme_path: Optional[str] = None

        for item in tree_items:
            if item.get("type") != "blob":
                continue
            path: str = item.get("path", "")
            parts = path.lower().split("/")
            if any(sd in parts for sd in _SKIP_DIRS):
                continue
            filename = parts[-1]
            if filename in _SKIP_NAMES:
                continue
            if filename in ("readme.md", "readme.rst", "readme.txt") and not readme_path:
                readme_path = path
                continue
            dot = filename.rfind(".")
            ext = filename[dot:] if dot >= 0 else ""
            cat = _EXT_TO_CAT.get(ext)
            if cat and len(buckets[cat]) < _CAPS[cat]:
                buckets[cat].append(path)

        # ── 2. Fetch file contents for each bucket ────────────────────────────
        def _fetch(path: str) -> Optional[str]:
            try:
                time.sleep(0.05)
                r = requests.get(
                    f"{base_url}/repos/{owner}/{repo_name}/contents/{path}",
                    headers=headers, params={"ref": branch}, timeout=15,
                )
                r.raise_for_status()
                data = r.json()
                raw = data.get("content", "")
                if data.get("encoding") == "base64":
                    return base64.b64decode(raw.replace("\n", "")).decode("utf-8", errors="replace")[:_MAX_CHARS]
                return (raw or "")[:_MAX_CHARS]
            except Exception as exc:
                logger.debug("[get_repo_metadata] fetch failed %s: %s", path, exc)
                return None

        def _to_file_list(paths: list[str], is_notebook: bool = False) -> list[dict]:
            out = []
            for p in paths:
                content = _fetch(p) or ""
                if is_notebook:
                    try:
                        nb_json = json.loads(content)
                        cells = nb_json.get("cells", [])
                        sources = []
                        for cell in cells:
                            if cell.get("cell_type") in ("code", "markdown"):
                                src = "".join(cell.get("source", []))
                                if src.strip():
                                    sources.append(f"[{cell['cell_type']}]\n{src}")
                        content = "\n\n".join(sources)
                    except Exception:
                        pass
                out.append({"path": p, "name": p.split("/")[-1], "content": content})
            return out

        readme_content = ""
        if readme_path:
            readme_content = _fetch(readme_path) or ""
        if not readme_content:
            # Fallback: try well-known names
            for rname in ("README.md", "readme.md", "README.rst"):
                c = self.get_file_content(owner, repo_name, rname)
                if c:
                    readme_content = c[:_MAX_CHARS]
                    break

        structure = self.get_repo_structure(owner, repo_name)

        return {
            "repo_name": repo_name,
            "owner": owner,
            "description": repo.description,
            "default_branch": branch,
            "languages": dict(repo.get_languages()),
            "structure": structure,
            "sql_files":      _to_file_list(buckets["sql_files"]),
            "python_files":   _to_file_list(buckets["python_files"]),
            "yaml_files":     _to_file_list(buckets["yaml_files"]),
            "json_files":     _to_file_list(buckets["json_files"]),
            "notebook_files": _to_file_list(buckets["notebook_files"], is_notebook=True),
            "readme": readme_content,
            "topics": list(repo.get_topics()),
            "created_at": repo.created_at.isoformat() if repo.created_at else None,
            "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
        }
