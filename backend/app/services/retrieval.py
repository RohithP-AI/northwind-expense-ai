"""
Policy retrieval service.

Embeds a natural-language question with OpenAI text-embedding-3-small and runs
a pgvector cosine-similarity search over policy_chunks, returning the top-K most
relevant chunks with a similarity score and a derived confidence level.

No LLM is involved — this is pure embedding search + retrieval. Answer
synthesis (calling Claude over the retrieved chunks) is a separate, later step.
"""

from dataclasses import dataclass

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.policy import PolicyChunk

# ── Confidence thresholds ─────────────────────────────────────────────────────
# text-embedding-3-small returns L2-normalized vectors, so cosine similarity is
# the dot product and lands roughly in [0, 1] for related text. These cutoffs
# are heuristics tuned for that model — adjust as retrieval quality is measured.
HIGH_SIMILARITY = 0.50
MEDIUM_SIMILARITY = 0.35


def similarity_to_confidence(similarity: float) -> str:
    if similarity >= HIGH_SIMILARITY:
        return "high"
    if similarity >= MEDIUM_SIMILARITY:
        return "medium"
    return "low"


@dataclass
class RetrievedChunk:
    document_id: str
    page_number: int | None
    section: str | None
    chunk_text: str
    similarity: float
    confidence: str


class RetrievalService:
    """Embedding search over the ingested policy corpus."""

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        # Lazily construct so importing this module doesn't require a key.
        if self._client is None:
            if not settings.OPENAI_API_KEY:
                raise RuntimeError(
                    "OPENAI_API_KEY is not set — cannot generate query embeddings."
                )
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    async def embed_query(self, query: str) -> list[float]:
        """Generate an embedding for the question (same model used at ingest)."""
        resp = await self.client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=query,
        )
        return resp.data[0].embedding

    async def search(
        self,
        db: AsyncSession,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        """
        Embed `query`, rank policy_chunks by cosine similarity, return top_k.

        pgvector's cosine_distance is 1 - cosine_similarity, so we convert back
        to a similarity score for the response.
        """
        embedding = await self.embed_query(query)

        distance = PolicyChunk.embedding.cosine_distance(embedding).label("distance")
        stmt = (
            select(PolicyChunk, distance)
            .where(PolicyChunk.embedding.is_not(None))
            .order_by(distance)
            .limit(top_k)
        )
        rows = (await db.execute(stmt)).all()

        results: list[RetrievedChunk] = []
        for chunk, dist in rows:
            similarity = 1.0 - float(dist)
            results.append(
                RetrievedChunk(
                    document_id=chunk.document_id,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    chunk_text=chunk.chunk_text,
                    similarity=round(similarity, 4),
                    confidence=similarity_to_confidence(similarity),
                )
            )
        return results


# Module-level singleton — the OpenAI client inside is created on first use.
retrieval_service = RetrievalService()
