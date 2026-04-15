"""
MCP Server for GitHub
Extracts code, structure, and metadata from GitHub repositories
"""
from github import Github, Repository
from typing import Optional
import base64
import json


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
            print(f"✅ Connected to GitHub as: {user.login}")
            self.connected = True
            return True
        except Exception as e:
            print(f"❌ Failed to connect to GitHub: {e}")
            self.connected = False
            return False
    
    def get_repo(self, owner: str, repo_name: str) -> Optional[Repository.Repository]:
        """Get a specific repository"""
        if not self.connected:
            raise Exception("Not connected to GitHub")
        try:
            return self.client.get_repo(f"{owner}/{repo_name}")
        except Exception as e:
            print(f"❌ Failed to get repo {owner}/{repo_name}: {e}")
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
            print(f"⚠️ Error getting contents: {e}")
        
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
            print(f"❌ Failed to get file {file_path}: {e}")
            return None
    
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
        """Get comprehensive metadata about a repository — all file types, full content"""
        repo = self.get_repo(owner, repo_name)
        if not repo:
            return {}
        
        structure = self.get_repo_structure(owner, repo_name)
        sql_files = self.get_sql_files(owner, repo_name)
        py_files = self.get_python_files(owner, repo_name)
        yaml_files = self.get_yaml_files(owner, repo_name)
        json_files = self.get_json_files(owner, repo_name)
        notebook_files = self.get_notebook_files(owner, repo_name)

        # Try to get README (also try readme.md lowercase)
        readme_content = (
            self.get_file_content(owner, repo_name, "README.md")
            or self.get_file_content(owner, repo_name, "readme.md")
            or ""
        )
        
        return {
            "repo_name": repo_name,
            "owner": owner,
            "description": repo.description,
            "default_branch": repo.default_branch,
            "languages": dict(repo.get_languages()),
            "structure": structure,
            "sql_files": sql_files,
            "python_files": py_files,
            "yaml_files": yaml_files,
            "json_files": json_files,
            "notebook_files": notebook_files,
            "readme": readme_content,
            "topics": list(repo.get_topics()),
            "created_at": repo.created_at.isoformat() if repo.created_at else None,
            "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
        }
