"""
Document processing module for parsing and chunking documents.
Supports PDF, TXT, and DOCX files.
"""
from pypdf import PdfReader
import docx
from typing import List, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DocumentChunk:
    """Represents a chunk of text from a document."""
    
    def __init__(
        self,
        text: str,
        chunk_index: int,
        start_char: int,
        end_char: int,
        metadata: dict = None
    ):
        self.text = text
        self.chunk_index = chunk_index
        self.start_char = start_char
        self.end_char = end_char
        self.metadata = metadata or {}


class DocumentProcessor:
    """Process documents: parse and chunk text."""
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ):
        """
        Initialize document processor.
        
        Args:
            chunk_size: Target size for each chunk (in characters)
            chunk_overlap: Overlap between consecutive chunks (in characters)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def parse_file(self, file_path: Path, file_type: str) -> str:
        """
        Parse document and extract text.
        
        Args:
            file_path: Path to the document file
            file_type: File type ('pdf', 'txt', 'docx')
            
        Returns:
            Extracted text content
        """
        if file_type == 'pdf':
            return self._parse_pdf(file_path)
        elif file_type == 'txt':
            return self._parse_txt(file_path)
        elif file_type == 'docx':
            return self._parse_docx(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
    
    def _parse_pdf(self, file_path: Path) -> str:
        """Extract text from PDF file."""
        logger.info(f"Parsing PDF: {file_path}")
        text = []
        
        with open(file_path, 'rb') as file:
            pdf_reader = PdfReader(file)
            for page_num, page in enumerate(pdf_reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
        
        return "\n\n".join(text)
    
    def _parse_txt(self, file_path: Path) -> str:
        """Extract text from TXT file."""
        logger.info(f"Parsing TXT: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    
    def _parse_docx(self, file_path: Path) -> str:
        """Extract text from DOCX file."""
        logger.info(f"Parsing DOCX: {file_path}")
        doc = docx.Document(file_path)
        text = []
        
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text.append(paragraph.text)
        
        return "\n\n".join(text)
    
    def chunk_text(self, text: str, metadata: dict = None) -> List[DocumentChunk]:
        """
        Split text into overlapping chunks.
        
        Args:
            text: Full document text
            metadata: Optional metadata to attach to each chunk
            
        Returns:
            List of DocumentChunk objects
        """
        if not text or len(text.strip()) == 0:
            return []
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(text):
            # Calculate end position
            end = start + self.chunk_size
            
            # If not the last chunk, try to break at a sentence or word boundary
            if end < len(text):
                # Look for sentence endings
                sentence_end = text.rfind('.', start, end)
                if sentence_end != -1 and sentence_end > start + self.chunk_size // 2:
                    end = sentence_end + 1
                else:
                    # Fall back to word boundary
                    space = text.rfind(' ', start, end)
                    if space != -1 and space > start + self.chunk_size // 2:
                        end = space
            
            # Extract chunk
            chunk_text = text[start:end].strip()
            
            if chunk_text:
                chunk = DocumentChunk(
                    text=chunk_text,
                    chunk_index=chunk_index,
                    start_char=start,
                    end_char=end,
                    metadata=metadata
                )
                chunks.append(chunk)
                chunk_index += 1
            
            # Move start position with overlap
            start = end - self.chunk_overlap
            if start < 0:
                start = 0
        
        logger.info(f"Created {len(chunks)} chunks from text (length: {len(text)})")
        return chunks


# Global document processor instance
_doc_processor: DocumentProcessor = None


def get_document_processor() -> DocumentProcessor:
    """Get or create the global document processor instance."""
    global _doc_processor
    if _doc_processor is None:
        _doc_processor = DocumentProcessor()
    return _doc_processor
