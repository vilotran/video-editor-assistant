"""Local vector indexing and semantic similarity search interface for VFX presets and rules."""

from __future__ import annotations

import math
import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _tokenize(text: str) -> list[str]:
    """Simple regex word tokenizer."""
    return re.findall(r"\b\w+\b", text.lower())


class LocalVectorStore:
    """In-memory cosine similarity vector index with Vertex AI Vector Search interface compatibility."""

    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []
        self._vocab: dict[str, int] = {}
        self._seed_default_knowledge()

    def _seed_default_knowledge(self) -> None:
        """Seeds default editing guidelines and VFX preset documentation."""
        self.add_document(
            doc_id="rule_layer_hierarchy",
            title="NLE Track Layering Rules",
            content="Upper video tracks (V2, V3) composite over lower tracks (V1). Place background footage on V1, B-roll or PiP windows on V2, and titles/graphics/cutouts on V3.",
            metadata={"category": "layering", "priority": "high"},
        )
        self.add_document(
            doc_id="rule_pip_framing",
            title="Picture in Picture Framing Best Practices",
            content="Position speaker or reaction facecam PiP in the top-right or bottom-right corner with 25-30% scale and rounded rectangle border for clean aesthetic.",
            metadata={"category": "pip", "priority": "standard"},
        )
        self.add_document(
            doc_id="rule_rotoscope_feather",
            title="Rotoscope Alpha Mask Feathering",
            content="Always apply 2.0 to 4.0 pixel feathering to character rotoscope alpha masks to prevent harsh digital edges and chatter.",
            metadata={"category": "mask", "priority": "standard"},
        )

    def _build_bow_vector(self, text: str) -> dict[str, float]:
        tokens = _tokenize(text)
        vec: dict[str, float] = {}
        for t in tokens:
            vec[t] = vec.get(t, 0.0) + 1.0
        # Normalize
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {k: v / norm for k, v in vec.items()}

    def add_document(self, doc_id: str, title: str, content: str, metadata: dict[str, Any]) -> None:
        """Indexes a document with its Bag-of-Words / embedding vector."""
        vec = self._build_bow_vector(f"{title} {content}")
        self.documents.append({
            "doc_id": doc_id,
            "title": title,
            "content": content,
            "metadata": metadata,
            "vector": vec,
        })

    def search(self, query: str, top_k: int = 2) -> list[dict[str, Any]]:
        """Finds top-k semantically relevant documents using cosine similarity."""
        query_vec = self._build_bow_vector(query)
        scored: list[tuple[float, dict[str, Any]]] = []

        for doc in self.documents:
            doc_vec = doc["vector"]
            # Cosine dot product
            score = sum(query_vec.get(term, 0.0) * weight for term, weight in doc_vec.items())
            if score > 0.0:
                scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, doc in scored[:top_k]:
            results.append({
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "content": doc["content"],
                "score": round(score, 4),
                "metadata": doc["metadata"],
            })
        return results


# Global vector store
vector_store = LocalVectorStore()
