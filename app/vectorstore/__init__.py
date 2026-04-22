"""
Vector Store Module
Manages ChromaDB for templates and repository content chunking and semantic search.
"""

from app.vectorstore.vector_manager import VectorStoreManager, get_vector_manager
from app.vectorstore.chunking_strategy import ChunkingStrategy, Chunk
from app.vectorstore.embeddings import EmbeddingModel
from app.vectorstore.retrieval import RetrievalAugmentedExtraction

__all__ = [
    'VectorStoreManager',
    'get_vector_manager',
    'ChunkingStrategy',
    'Chunk',
    'EmbeddingModel',
    'RetrievalAugmentedExtraction',
]
