"""
Chunking Strategy for Different Content Types
Splits content into chunks with overlap, preserving metadata
"""
from typing import Optional, TypedDict
import re


class Chunk(TypedDict):
    """Represents a single chunk of content."""
    content: str
    metadata: dict


class ChunkingStrategy:
    """
    Implements different chunking strategies for different content types.
    All strategies use overlap to preserve context across chunk boundaries.
    """
    
    # Chunk size config (in characters)
    TEMPLATE_CHUNK_SIZE = 2500
    TEMPLATE_CHUNK_OVERLAP = 300
    
    CODE_CHUNK_SIZE = 2500
    CODE_CHUNK_OVERLAP = 300
    
    DOC_CHUNK_SIZE = 2000
    DOC_CHUNK_OVERLAP = 200
    
    @staticmethod
    def _split_with_overlap(
        text: str,
        chunk_size: int,
        overlap: int
    ) -> list[str]:
        """
        Split text into chunks with overlap.
        Args:
            text: Text to split
            chunk_size: Characters per chunk
            overlap: Characters to overlap between chunks
        Returns:
            List of chunks
        """
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            if end >= len(text):
                break
            start = end - overlap
        
        return chunks
    
    @classmethod
    def chunk_template(cls, template_text: str, template_title: str = "Unknown") -> list[Chunk]:
        """
        Chunk a template with generous overlap to preserve field context.
        Args:
            template_text: Full template text
            template_title: Title/name of template
        Returns:
            List of chunks with metadata
        """
        raw_chunks = cls._split_with_overlap(
            template_text,
            cls.TEMPLATE_CHUNK_SIZE,
            cls.TEMPLATE_CHUNK_OVERLAP
        )
        
        chunks: list[Chunk] = []
        for i, chunk in enumerate(raw_chunks):
            chunks.append({
                "content": chunk,
                "metadata": {
                    "type": "template",
                    "title": template_title,
                    "chunk_index": i,
                    "total_chunks": len(raw_chunks),
                    "chunk_size": len(chunk),
                }
            })
        
        return chunks
    
    @classmethod
    def chunk_code_file(
        cls,
        file_content: str,
        file_path: str,
        language: str = "unknown"
    ) -> list[Chunk]:
        """
        Chunk code files (Python, SQL, etc.) intelligently.
        Tries to split at logical boundaries (functions, classes, methods).
        Args:
            file_content: Full file content
            file_path: Path/name of file
            language: Programming language ('python', 'sql', 'yaml', etc.)
        Returns:
            List of chunks with metadata
        """
        # Try semantic split first (by functions/classes for Python)
        if language.lower() == "python":
            semantic_chunks = cls._split_python_code(file_content)
        elif language.lower() == "sql":
            semantic_chunks = cls._split_sql_code(file_content)
        else:
            semantic_chunks = None
        
        # If semantic split produced reasonable chunks, use them
        if semantic_chunks and len(semantic_chunks) > 1:
            raw_chunks = semantic_chunks
        else:
            # Fall back to character-based splitting
            raw_chunks = cls._split_with_overlap(
                file_content,
                cls.CODE_CHUNK_SIZE,
                cls.CODE_CHUNK_OVERLAP
            )
        
        chunks: list[Chunk] = []
        for i, chunk in enumerate(raw_chunks):
            chunks.append({
                "content": chunk,
                "metadata": {
                    "type": "code",
                    "file_path": file_path,
                    "language": language,
                    "chunk_index": i,
                    "total_chunks": len(raw_chunks),
                    "chunk_size": len(chunk),
                }
            })
        
        return chunks
    
    @classmethod
    def chunk_documentation(
        cls,
        doc_content: str,
        doc_name: str
    ) -> list[Chunk]:
        """
        Chunk documentation (README, markdown files) preserving section structure.
        Args:
            doc_content: Full document content
            doc_name: Name/path of document
        Returns:
            List of chunks with metadata
        """
        # Try to split by markdown headers
        header_chunks = cls._split_by_markdown_headers(doc_content)
        
        if header_chunks and len(header_chunks) > 1:
            # Further chunk if any section is too large
            raw_chunks = []
            for section_text in header_chunks:
                if len(section_text) > cls.DOC_CHUNK_SIZE:
                    raw_chunks.extend(cls._split_with_overlap(
                        section_text,
                        cls.DOC_CHUNK_SIZE,
                        cls.DOC_CHUNK_OVERLAP
                    ))
                else:
                    raw_chunks.append(section_text)
        else:
            raw_chunks = cls._split_with_overlap(
                doc_content,
                cls.DOC_CHUNK_SIZE,
                cls.DOC_CHUNK_OVERLAP
            )
        
        chunks: list[Chunk] = []
        for i, chunk in enumerate(raw_chunks):
            chunks.append({
                "content": chunk,
                "metadata": {
                    "type": "documentation",
                    "doc_name": doc_name,
                    "chunk_index": i,
                    "total_chunks": len(raw_chunks),
                    "chunk_size": len(chunk),
                }
            })
        
        return chunks
    
    @staticmethod
    def _split_python_code(code: str) -> Optional[list[str]]:
        """
        Try to split Python code at function/class definitions.
        Returns None if split fails or produces too few chunks.
        """
        try:
            # Split by function/class definitions
            pattern = r'^(class |def |\n\n\n)'
            parts = re.split(pattern, code, flags=re.MULTILINE)
            
            # Reconstruct chunks (the pattern captures the separators)
            chunks = []
            for i in range(0, len(parts) - 1, 2):
                if i + 1 < len(parts):
                    chunk = parts[i] + parts[i + 1]
                    if chunk.strip():
                        chunks.append(chunk)
            
            # Return only if we got reasonable chunks
            return chunks if len(chunks) > 1 else None
        except Exception:
            return None
    
    @staticmethod
    def _split_sql_code(code: str) -> Optional[list[str]]:
        """
        Try to split SQL code at statement boundaries (SELECT, INSERT, CREATE, etc.).
        Returns None if split fails or produces too few chunks.
        """
        try:
            # Split by SQL statement keywords
            pattern = r'^(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|WITH|\n\n)'
            parts = re.split(pattern, code, flags=re.MULTILINE | re.IGNORECASE)
            
            chunks = []
            for i in range(0, len(parts) - 1, 2):
                if i + 1 < len(parts):
                    chunk = parts[i] + parts[i + 1]
                    if chunk.strip():
                        chunks.append(chunk)
            
            return chunks if len(chunks) > 1 else None
        except Exception:
            return None
    
    @staticmethod
    def _split_by_markdown_headers(text: str) -> Optional[list[str]]:
        """
        Split markdown content by headers (# ## ###).
        Returns None if split fails or produces too few chunks.
        """
        try:
            # Split by markdown headers
            pattern = r'^(#{1,6}\s+)'
            parts = re.split(pattern, text, flags=re.MULTILINE)
            
            chunks = []
            for i in range(0, len(parts) - 1, 2):
                if i + 1 < len(parts):
                    chunk = parts[i] + parts[i + 1]
                    if chunk.strip():
                        chunks.append(chunk)
            
            return chunks if len(chunks) > 1 else None
        except Exception:
            return None
