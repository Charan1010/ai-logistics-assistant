"""
Embeddings module for document vectorization.
Uses sentence-transformers for generating embeddings.
"""
from typing import List
import logging
import ssl
import os

from app.config import settings

logger = logging.getLogger(__name__)

# These must be set BEFORE importing sentence_transformers/huggingface_hub — that
# library reads them once at import time, so setting them afterward has no effect.
# Only forced when embeddings_offline_mode=True (opt-in via .env) — on CI/fresh
# machines with no cached model, forcing offline mode here would break entirely.
if settings.embeddings_offline_mode:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    # Disable SSL verification for HuggingFace downloads (corporate environment workaround)
    os.environ.setdefault("CURL_CA_BUNDLE", "")
    os.environ.setdefault("REQUESTS_CA_BUNDLE", "")
    os.environ.setdefault("SSL_CERT_FILE", "")
    os.environ.setdefault("HTTPX_NO_VERIFY_SSL", "1")

    # Create unverified SSL context
    ssl._create_default_https_context = ssl._create_unverified_context

from sentence_transformers import SentenceTransformer  # noqa: E402 (must follow env setup above)


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
        # HF_HUB_OFFLINE=1 (set above) forces the cached model to load without network calls
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
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
