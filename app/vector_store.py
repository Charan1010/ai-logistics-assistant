"""
Vector store module using ChromaDB for document storage and retrieval.
"""
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Optional
from datetime import datetime
import uuid
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class VectorStore:
    """Manages document storage and retrieval in ChromaDB."""
    
    def __init__(self, persist_directory: str = "./data/chroma"):
        """
        Initialize ChromaDB vector store.
        
        Args:
            persist_directory: Directory to persist the database
        """
        self.persist_directory = persist_directory
        Path(persist_directory).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initializing ChromaDB at: {persist_directory}")
        
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Create or get collection
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"description": "Logistics documents collection"}
        )
        
        logger.info(f"ChromaDB initialized. Collection 'documents' ready.")
    
    def add_document(
        self,
        document_id: str,
        filename: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Add document chunks to the vector store.
        
        Args:
            document_id: Unique document identifier
            filename: Original filename
            chunks: List of text chunks
            embeddings: List of embedding vectors (one per chunk)
            metadata: Optional document metadata
            
        Returns:
            Number of chunks added
        """
        if len(chunks) != len(embeddings):
            raise ValueError("Number of chunks must match number of embeddings")
        
        base_metadata = metadata or {}
        base_metadata.update({
            "document_id": document_id,
            "filename": filename,
            "upload_date": datetime.now().isoformat()
        })
        
        # Create unique IDs for each chunk
        chunk_ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
        
        # Prepare metadata for each chunk
        chunk_metadatas = []
        for i in range(len(chunks)):
            chunk_meta = base_metadata.copy()
            chunk_meta["chunk_index"] = i
            chunk_meta["total_chunks"] = len(chunks)
            chunk_metadatas.append(chunk_meta)
        
        # Add to collection
        self.collection.add(
            ids=chunk_ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=chunk_metadatas
        )
        
        logger.info(f"Added document {document_id} with {len(chunks)} chunks")
        return len(chunks)
    
    def search(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        document_id: Optional[str] = None
    ) -> Dict:
        """
        Search for similar chunks using vector similarity.
        
        Args:
            query_embedding: Query embedding vector
            n_results: Number of results to return
            document_id: Optional filter by document ID
            
        Returns:
            Dict with ids, documents, distances, and metadatas
        """
        where_filter = None
        if document_id:
            where_filter = {"document_id": document_id}
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter
        )
        
        return results
    
    def get_document_chunks(self, document_id: str) -> List[Dict]:
        """
        Get all chunks for a specific document.
        
        Args:
            document_id: Document identifier
            
        Returns:
            List of chunks with their metadata
        """
        results = self.collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"]
        )
        
        if not results['ids']:
            return []
        
        chunks = []
        for i in range(len(results['ids'])):
            chunks.append({
                "id": results['ids'][i],
                "text": results['documents'][i],
                "metadata": results['metadatas'][i]
            })
        
        # Sort by chunk index
        chunks.sort(key=lambda x: x['metadata'].get('chunk_index', 0))
        return chunks
    
    def delete_document(self, document_id: str) -> int:
        """
        Delete all chunks for a document.
        
        Args:
            document_id: Document identifier
            
        Returns:
            Number of chunks deleted
        """
        # Get all chunk IDs for this document
        results = self.collection.get(
            where={"document_id": document_id},
            include=[]
        )
        
        chunk_ids = results['ids']
        
        if chunk_ids:
            self.collection.delete(ids=chunk_ids)
            logger.info(f"Deleted document {document_id} ({len(chunk_ids)} chunks)")
        
        return len(chunk_ids)
    
    def list_documents(self) -> List[Dict]:
        """
        List all unique documents in the store.
        
        Returns:
            List of document metadata
        """
        # Get all items
        results = self.collection.get(include=["metadatas"])
        
        if not results['metadatas']:
            return []
        
        # Extract unique documents
        docs_dict = {}
        for metadata in results['metadatas']:
            doc_id = metadata.get('document_id')
            if doc_id and doc_id not in docs_dict:
                docs_dict[doc_id] = {
                    "document_id": doc_id,
                    "filename": metadata.get('filename'),
                    "upload_date": metadata.get('upload_date'),
                    "total_chunks": metadata.get('total_chunks', 0)
                }
        
        return list(docs_dict.values())
    
    def get_stats(self) -> Dict:
        """Get collection statistics."""
        count = self.collection.count()
        documents = self.list_documents()
        
        return {
            "total_chunks": count,
            "total_documents": len(documents),
            "collection_name": self.collection.name
        }


# Global vector store instance
_vector_store: VectorStore = None


def get_vector_store() -> VectorStore:
    """Get or create the global vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
