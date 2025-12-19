from sentence_transformers import SentenceTransformer
from typing import Optional
import numpy as np
from loguru import logger
from config import settings


class EmbeddingModel:

    _instance: Optional['EmbeddingModel'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'model'):
            logger.info(f"Loading embedding model: {settings.MODEL_NAME}")
            self.model = SentenceTransformer(settings.MODEL_NAME)
            self.dimension = settings.EMBEDDING_DIMENSION
            logger.info(f"Model loaded successfully. Dimension: {self.dimension}")
    
    def encode(self, texts: str | list[str], batch_size: int = 32) -> np.ndarray:
        """
        Generate embeddings for text(s)
        
        Args:
            texts: Single text or list of texts
            batch_size: Batch size for encoding
            
        Returns:
            Embeddings as numpy array
        """
        if isinstance(texts, str):
            texts = [texts]
        
        # Filter out None and empty strings
        valid_texts = [t for t in texts if t and t.strip()]
        
        if not valid_texts:
            # Return zero vector if no valid text
            return np.zeros((len(texts), self.dimension))
        
        embeddings = self.model.encode(
            valid_texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        
        return embeddings
    
    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding
            embedding2: Second embedding
            
        Returns:
            Cosine similarity score
        """
        # Normalize embeddings
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        # Cosine similarity
        similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)
        return float(similarity)
    
    def compute_similarities(self, query_embedding: np.ndarray, embeddings: np.ndarray) -> np.ndarray:
        """
        Compute cosine similarities between query and multiple embeddings
        
        Args:
            query_embedding: Query embedding (1D array)
            embeddings: Matrix of embeddings (2D array)
            
        Returns:
            Array of similarity scores
        """
        # Normalize query
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-10)
        
        # Normalize all embeddings
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-10
        normalized_embeddings = embeddings / norms
        
        # Compute similarities
        similarities = np.dot(normalized_embeddings, query_norm)
        
        return similarities


# Singleton instance
embedding_model = EmbeddingModel()
