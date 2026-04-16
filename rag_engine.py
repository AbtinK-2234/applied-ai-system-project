"""
RAG Engine for PawPal+

Loads pet-care knowledge documents, chunks them, indexes with TF-IDF,
and retrieves the most relevant chunks for a given query.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_DIR = Path(__file__).parent / "knowledge_base"
CHUNK_SIZE = 600  # approximate characters per chunk
CHUNK_OVERLAP = 100
TOP_K = 4  # number of chunks to retrieve


@dataclass
class Chunk:
    """A single chunk of text from the knowledge base."""
    text: str
    source: str  # filename it came from
    heading: str  # nearest heading above this chunk


@dataclass
class RAGEngine:
    """Retrieval-Augmented Generation engine using TF-IDF similarity."""

    chunks: list[Chunk] = field(default_factory=list)
    _vectorizer: TfidfVectorizer | None = field(default=None, repr=False)
    _tfidf_matrix: object = field(default=None, repr=False)

    def load_knowledge_base(self, directory: Path | None = None) -> int:
        """Load and chunk all markdown files from the knowledge base directory.

        Returns the number of chunks created.
        """
        kb_dir = directory or KNOWLEDGE_BASE_DIR
        if not kb_dir.exists():
            logger.error("Knowledge base directory not found: %s", kb_dir)
            return 0

        md_files = sorted(kb_dir.glob("*.md"))
        if not md_files:
            logger.warning("No markdown files found in %s", kb_dir)
            return 0

        self.chunks = []
        for md_file in md_files:
            try:
                text = md_file.read_text(encoding="utf-8")
                file_chunks = self._chunk_markdown(text, md_file.name)
                self.chunks.extend(file_chunks)
                logger.info(
                    "Loaded %d chunks from %s", len(file_chunks), md_file.name
                )
            except Exception:
                logger.exception("Failed to load %s", md_file.name)

        if self.chunks:
            self._build_index()
            logger.info(
                "Knowledge base ready: %d chunks from %d files",
                len(self.chunks),
                len(md_files),
            )
        return len(self.chunks)

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk_markdown(text: str, source: str) -> list[Chunk]:
        """Split markdown text into overlapping chunks, preserving headings."""
        lines = text.split("\n")
        chunks: list[Chunk] = []
        current_heading = source.replace(".md", "").replace("_", " ").title()
        current_block: list[str] = []
        current_len = 0

        for line in lines:
            # Track the nearest heading
            stripped = line.strip()
            if stripped.startswith("#"):
                # If we have accumulated text, flush it as a chunk
                if current_block:
                    chunks.append(Chunk(
                        text="\n".join(current_block).strip(),
                        source=source,
                        heading=current_heading,
                    ))
                    # Keep overlap: last few lines
                    overlap_text = "\n".join(current_block).strip()
                    if len(overlap_text) > CHUNK_OVERLAP:
                        tail = overlap_text[-CHUNK_OVERLAP:]
                        current_block = [tail]
                        current_len = len(tail)
                    else:
                        current_block = []
                        current_len = 0
                current_heading = stripped.lstrip("#").strip()

            current_block.append(line)
            current_len += len(line)

            # Flush when chunk is large enough
            if current_len >= CHUNK_SIZE:
                chunks.append(Chunk(
                    text="\n".join(current_block).strip(),
                    source=source,
                    heading=current_heading,
                ))
                overlap_text = "\n".join(current_block).strip()
                if len(overlap_text) > CHUNK_OVERLAP:
                    tail = overlap_text[-CHUNK_OVERLAP:]
                    current_block = [tail]
                    current_len = len(tail)
                else:
                    current_block = []
                    current_len = 0

        # Final block
        if current_block:
            final_text = "\n".join(current_block).strip()
            if final_text:
                chunks.append(Chunk(
                    text=final_text,
                    source=source,
                    heading=current_heading,
                ))

        # Drop trivially small chunks
        return [c for c in chunks if len(c.text) > 30]

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        """Build a TF-IDF index over all chunks."""
        corpus = [f"{c.heading} {c.text}" for c in self.chunks]
        self._vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=5000,
            ngram_range=(1, 2),
        )
        self._tfidf_matrix = self._vectorizer.fit_transform(corpus)
        logger.info("TF-IDF index built with %d features", len(self._vectorizer.get_feature_names_out()))

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(self, query: str, top_k: int = TOP_K) -> list[Chunk]:
        """Return the top-k most relevant chunks for the given query."""
        if not self.chunks or self._vectorizer is None or self._tfidf_matrix is None:
            logger.warning("retrieve() called before index was built")
            return []

        query_vec = self._vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self._tfidf_matrix).flatten()

        # Get top-k indices sorted by score descending
        top_indices = scores.argsort()[::-1][:top_k]
        results = []
        for idx in top_indices:
            if scores[idx] > 0.0:  # only include chunks with nonzero relevance
                results.append(self.chunks[idx])
                logger.debug(
                    "Retrieved chunk (score=%.3f) from %s [%s]",
                    scores[idx],
                    self.chunks[idx].source,
                    self.chunks[idx].heading,
                )
        if not results:
            logger.info("No relevant chunks found for query: %s", query[:80])
        return results

    def format_context(self, chunks: list[Chunk]) -> str:
        """Format retrieved chunks into a context string for the LLM."""
        if not chunks:
            return ""
        sections = []
        for i, chunk in enumerate(chunks, 1):
            sections.append(
                f"[Source {i}: {chunk.source} - {chunk.heading}]\n{chunk.text}"
            )
        return "\n\n---\n\n".join(sections)
