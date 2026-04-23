"""
Embedding Configuration for ChromaDB
Uses Sentence Transformers for efficient, lightweight embeddings suitable for semantic search
"""
from sentence_transformers import SentenceTransformer
from typing import Optional


class EmbeddingModel:
    """Wrapper for SentenceTransformer embedding model."""
    
    _model_instance: Optional[SentenceTransformer] = None
    _model_name: str = "all-MiniLM-L6-v2"  # Lightweight model: 22M params, 384 dims
    
    @classmethod
    def get_model(cls) -> SentenceTransformer:
        """Get or create the embedding model instance (singleton)."""
        if cls._model_instance is None:
            cls._model_instance = SentenceTransformer(cls._model_name)
        return cls._model_instance
    
    @classmethod
    def embed(cls, text: str) -> list[float]:
        """
        Embed a single piece of text.
        Args:
            text: Text to embed
        Returns:
            Embedding vector (384 dimensions for all-MiniLM-L6-v2)
        """
        model = cls.get_model()
        embedding = model.encode(text, convert_to_numpy=False)
        return embedding.tolist()
    
    @classmethod
    def embed_batch(cls, texts: list[str]) -> list[list[float]]:
        """
        Embed multiple texts efficiently in batch.
        Args:
            texts: List of texts to embed
        Returns:
            List of embedding vectors
        """
        model = cls.get_model()
        embeddings = model.encode(texts, convert_to_numpy=False)
        return [emb.tolist() for emb in embeddings]
