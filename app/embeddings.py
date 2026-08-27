"""
Embeddings module for document vectorization.
Uses sentence-transformers for generating embeddings.
"""
from sentence_transformers import SentenceTransformer
from typing import List
import logging
import ssl
import os
import certifi

logger = logging.getLogger(__name__)

# Disable SSL verification for HuggingFace downloads (corporate environment workaround)
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["REQUESTS_CA_BUNDLE"] = ""
os.environ["SSL_CERT_FILE"] = ""
os.environ["HTTPX_NO_VERIFY_SSL"] = "1"

# Create unverified SSL context
ssl._create_default_https_context = ssl._create_unverified_context

# Also set for httpx which HuggingFace Hub uses
import httpx
original_client_init = httpx.Client.__init__

def patched_client_init(self, *args, **kwargs):
    kwargs['verify'] = False
    original_client_init(self, *args, **kwargs)

httpx.Client.__init__ = patched_client_init


class EmbeddingModel:
    """Wrapper for sentence-transformer embedding model."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize embedding model.
        
        Args:
            model_name: HuggingFace model name for embeddings
                       Default: all-MiniLM-L6-v2 (fast, 384 dimensions)
        """
        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_embedding_dimension()
        logger.info(f"Embedding model loaded. Dimension: {self.dimension}")
    
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Input text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts efficiently.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=True)
        return embeddings.tolist()


# Global embedding model instance
_embedding_model: EmbeddingModel = None


def get_embedding_model() -> EmbeddingModel:
    """Get or create the global embedding model instance."""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = EmbeddingModel()
    return _embedding_model
