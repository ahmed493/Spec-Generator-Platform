"""
MCP Server for GitHub
Extracts code, structure, and metadata from GitHub repositories
"""
from github import Github, Repository
from typing import Optional
import base64


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
    
    def get_repo_metadata(self, owner: str, repo_name: str) -> dict:
        """Get comprehensive metadata about a repository"""
        repo = self.get_repo(owner, repo_name)
        if not repo:
            return {}
        
        structure = self.get_repo_structure(owner, repo_name)
        sql_files = self.get_sql_files(owner, repo_name)
        py_files = self.get_python_files(owner, repo_name)
        
        # Try to get README
        readme_content = self.get_file_content(owner, repo_name, "README.md")
        
        return {
            "repo_name": repo_name,
            "owner": owner,
            "description": repo.description,
            "default_branch": repo.default_branch,
            "languages": dict(repo.get_languages()),
            "structure": structure,
            "sql_files": sql_files,
            "python_files": py_files,
            "readme": readme_content,
            "topics": list(repo.get_topics()),
            "created_at": repo.created_at.isoformat() if repo.created_at else None,
            "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
        }
