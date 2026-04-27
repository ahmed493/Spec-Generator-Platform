"""
Vector Store Manager using ChromaDB
Manages two separate collections:
1. Templates Collection - for storing parsed templates with their chunks
2. Repository Content Collection - for storing repository file content chunks
"""
import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import Optional
import json
import uuid
import os

from app.vectorstore.embeddings import EmbeddingModel
from app.vectorstore.chunking_strategy import ChunkingStrategy, Chunk


class VectorStoreManager:
    """
    Manages ChromaDB collections for templates and repository content.
    Uses persistent storage in ./data/chroma/ directory.
    """
    
    def __init__(self, persist_dir: str = "./data/chroma"):
        """
        Initialize ChromaDB client with persistent storage.
        Args:
            persist_dir: Directory for persistent ChromaDB storage
        """
        os.makedirs(persist_dir, exist_ok=True)
        
        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(path=persist_dir)
        
        # Get or create collections
        self.templates_collection = self.client.get_or_create_collection(
            name="templates_collection",
            metadata={"hnsw:space": "cosine"}
        )
        
        self.content_collection = self.client.get_or_create_collection(
            name="repository_content_collection",
            metadata={"hnsw:space": "cosine"}
        )
    
    # ==================== TEMPLATES ====================
    
    def add_template(self, template_text: str, template_title: str, project_id: str) -> dict:
        """
        Add a template to the vector store.
        Chunks the template and stores all chunks with metadata.
        
        Args:
            template_text: Full template text
            template_title: Title of the template
            project_id: ID of the project this template belongs to
            
        Returns:
            dict with template_id and number of chunks added
        """
        # Chunk the template
        chunks = ChunkingStrategy.chunk_template(template_text, template_title)
        
        template_id = str(uuid.uuid4())
        ids = []
        documents = []
        metadatas = []
        
        for chunk in chunks:
            chunk_id = f"{template_id}_chunk_{chunk['metadata']['chunk_index']}"
            ids.append(chunk_id)
            documents.append(chunk['content'])
            
            # Add project_id and template_id to metadata
            metadata = {
                **chunk['metadata'],
                "project_id": project_id,
                "template_id": template_id,
            }
            metadatas.append(metadata)
        
        # Add to ChromaDB
        self.templates_collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
        
        return {
            "template_id": template_id,
            "project_id": project_id,
            "title": template_title,
            "chunks_added": len(chunks),
        }
    
    def search_templates(self, query: str, project_id: str, top_k: int = 5) -> list[dict]:
        """
        Search for templates similar to the query.
        Args:
            query: Search query
            project_id: Filter by project ID
            top_k: Number of results to return
            
        Returns:
            List of similar template chunks with scores
        """
        results = self.templates_collection.query(
            query_texts=[query],
            where={"project_id": {"$eq": project_id}},
            n_results=top_k
        )
        
        return self._format_search_results(results)
    
    def get_all_templates(self, project_id: str) -> list[dict]:
        """
        Get all template chunks for a project.
        Args:
            project_id: Filter by project ID
            
        Returns:
            List of template chunks
        """
        results = self.templates_collection.get(
            where={"project_id": {"$eq": project_id}}
        )
        
        # Group by template_id
        templates = {}
        for i, doc in enumerate(results['documents']):
            meta = results['metadatas'][i]
            template_id = meta.get('template_id')
            if template_id not in templates:
                templates[template_id] = {
                    "template_id": template_id,
                    "title": meta.get('title', 'Unknown'),
                    "chunks": []
                }
            templates[template_id]["chunks"].append({
                "chunk_index": meta.get('chunk_index'),
                "content": doc,
                "metadata": meta
            })
        
        return list(templates.values())
    
    # ==================== REPOSITORY CONTENT ====================
    
    def add_repository_content(
        self,
        file_content: str,
        file_path: str,
        file_type: str,
        project_id: str,
        repo_name: str
    ) -> dict:
        """
        Add repository file content to the vector store.
        Chunks the content and stores all chunks with metadata.
        
        Args:
            file_content: Full file content
            file_path: Path of the file in repository
            file_type: Type of file ('python', 'sql', 'yaml', 'json', 'markdown', etc.)
            project_id: ID of the project
            repo_name: Name of the repository
            
        Returns:
            dict with file_id and number of chunks added
        """
        # Determine chunking strategy based on file type
        if file_type.lower() in ['py', 'python']:
            chunks = ChunkingStrategy.chunk_code_file(file_content, file_path, 'python')
        elif file_type.lower() in ['sql']:
            chunks = ChunkingStrategy.chunk_code_file(file_content, file_path, 'sql')
        elif file_type.lower() in ['md', 'markdown', 'readme', 'txt']:
            chunks = ChunkingStrategy.chunk_documentation(file_content, file_path)
        elif file_type.lower() in ['yaml', 'yml', 'json']:
            chunks = ChunkingStrategy.chunk_documentation(file_content, file_path)
        else:
            # Default: treat as documentation
            chunks = ChunkingStrategy.chunk_documentation(file_content, file_path)
        
        file_id = str(uuid.uuid4())
        ids = []
        documents = []
        metadatas = []
        
        for chunk in chunks:
            chunk_id = f"{file_id}_chunk_{chunk['metadata']['chunk_index']}"
            ids.append(chunk_id)
            documents.append(chunk['content'])
            
            # Add project_id, repo_name, and file_id to metadata
            metadata = {
                **chunk['metadata'],
                "project_id": project_id,
                "repo_name": repo_name,
                "file_id": file_id,
            }
            metadatas.append(metadata)
        
        # Add to ChromaDB
        self.content_collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
        
        return {
            "file_id": file_id,
            "project_id": project_id,
            "file_path": file_path,
            "file_type": file_type,
            "repo_name": repo_name,
            "chunks_added": len(chunks),
        }
    
    def add_multiple_repository_files(
        self,
        files: list[dict],
        project_id: str,
        repo_name: str
    ) -> list[dict]:
        """
        Add multiple repository files to vector store.
        Args:
            files: List of dicts with keys: content, path, type
            project_id: ID of the project
            repo_name: Name of the repository
            
        Returns:
            List of added file results
        """
        results = []
        for file_info in files:
            try:
                result = self.add_repository_content(
                    file_content=file_info.get('content', ''),
                    file_path=file_info.get('path', 'unknown'),
                    file_type=file_info.get('type', 'unknown'),
                    project_id=project_id,
                    repo_name=repo_name
                )
                results.append(result)
            except Exception as e:
                results.append({
                    "file_path": file_info.get('path'),
                    "error": str(e)
                })
        
        return results
    
    def search_repository_content(
        self,
        query: str,
        project_id: str,
        top_k: int = 10,
        file_type: Optional[str] = None
    ) -> list[dict]:
        """
        Search for repository content similar to the query.
        Args:
            query: Search query
            project_id: Filter by project ID
            top_k: Number of results to return
            file_type: Optional filter by file type
            
        Returns:
            List of similar content chunks with scores
        """
        where_clause = {"project_id": {"$eq": project_id}}
        if file_type:
            where_clause["file_type"] = {"$eq": file_type}
        
        results = self.content_collection.query(
            query_texts=[query],
            where=where_clause,
            n_results=top_k
        )
        
        return self._format_search_results(results)
    
    def get_all_repository_content(self, project_id: str) -> list[dict]:
        """
        Get all repository content chunks for a project.
        Args:
            project_id: Filter by project ID
            
        Returns:
            List of content chunks grouped by file
        """
        results = self.content_collection.get(
            where={"project_id": {"$eq": project_id}}
        )
        
        # Group by file_id
        files = {}
        for i, doc in enumerate(results['documents']):
            meta = results['metadatas'][i]
            file_id = meta.get('file_id')
            if file_id not in files:
                files[file_id] = {
                    "file_id": file_id,
                    "file_path": meta.get('file_path', 'unknown'),
                    "file_type": meta.get('file_type', 'unknown'),
                    "repo_name": meta.get('repo_name', 'unknown'),
                    "chunks": []
                }
            files[file_id]["chunks"].append({
                "chunk_index": meta.get('chunk_index'),
                "content": doc,
                "metadata": meta
            })
        
        return list(files.values())
    
    def get_file_content(self, file_id: str) -> Optional[dict]:
        """
        Get full reconstructed file content from chunks.
        Args:
            file_id: ID of the file
            
        Returns:
            dict with file_path, file_type, and full_content
        """
        results = self.content_collection.get(
            where={"file_id": {"$eq": file_id}}
        )
        
        if not results['documents']:
            return None
        
        # Reconstruct file from chunks
        chunks_dict = {}
        metadata = None
        for i, doc in enumerate(results['documents']):
            meta = results['metadatas'][i]
            chunk_idx = meta.get('chunk_index', 0)
            chunks_dict[chunk_idx] = doc
            if metadata is None:
                metadata = meta
        
        # Sort chunks by index and concatenate
        sorted_chunks = [chunks_dict[i] for i in sorted(chunks_dict.keys())]
        # Note: chunks have overlap, so simple concatenation will have duplicates
        # A more sophisticated merge would be needed for perfect reconstruction
        full_content = "\n".join(sorted_chunks)
        
        return {
            "file_id": file_id,
            "file_path": metadata.get('file_path') if metadata else 'unknown',
            "file_type": metadata.get('file_type') if metadata else 'unknown',
            "full_content": full_content,
            "num_chunks": len(sorted_chunks)
        }
    
    # ==================== UTILITIES ====================
    
    def _format_search_results(self, results: dict) -> list[dict]:
        """
        Format ChromaDB query results into a nicer structure.
        """
        formatted = []
        
        if not results['documents'] or not results['documents'][0]:
            return formatted
        
        for i, doc in enumerate(results['documents'][0]):
            distance = results['distances'][0][i] if results['distances'] else 0
            # Convert distance to similarity score (cosine distance -> similarity)
            similarity = 1 - distance
            
            formatted.append({
                "content": doc,
                "similarity_score": round(similarity, 3),
                "distance": round(distance, 3),
                "metadata": results['metadatas'][0][i] if results['metadatas'] else {}
            })
        
        return formatted
    
    def clear_project(self, project_id: str) -> dict:
        """
        Clear all vectors for a specific project.
        Args:
            project_id: ID of the project to clear
            
        Returns:
            Summary of cleared items
        """
        # Delete from templates
        template_ids = self.templates_collection.get(
            where={"project_id": {"$eq": project_id}}
        )['ids']
        
        # Delete from content
        content_ids = self.content_collection.get(
            where={"project_id": {"$eq": project_id}}
        )['ids']
        
        if template_ids:
            self.templates_collection.delete(ids=template_ids)
        
        if content_ids:
            self.content_collection.delete(ids=content_ids)
        
        return {
            "project_id": project_id,
            "templates_cleared": len(template_ids),
            "content_chunks_cleared": len(content_ids),
        }
    
    def get_statistics(self) -> dict:
        """Get statistics about the vector stores."""
        template_count = self.templates_collection.count()
        content_count = self.content_collection.count()
        
        return {
            "templates_collection": {
                "total_chunks": template_count,
            },
            "content_collection": {
                "total_chunks": content_count,
            },
            "total_chunks": template_count + content_count,
        }


# Global instance (singleton pattern)
_vector_manager: Optional[VectorStoreManager] = None


def get_vector_manager() -> VectorStoreManager:
    """Get or create the global VectorStoreManager instance."""
    global _vector_manager
    if _vector_manager is None:
        _vector_manager = VectorStoreManager()
    return _vector_manager
