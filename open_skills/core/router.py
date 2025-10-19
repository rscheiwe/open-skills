"""
Skill Router for embedding-based skill discovery and auto-selection.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID

import httpx
from sqlalchemy import select, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from open_skills.config import settings
from open_skills.core.exceptions import EmbeddingError
from open_skills.core.telemetry import get_logger, trace_operation
from open_skills.db.models import SkillVersion, Skill

logger = get_logger(__name__)


class SkillRouter:
    """Routes queries to appropriate skills using embeddings and metadata."""

    def __init__(self, db: AsyncSession):
        """
        Initialize skill router.

        Args:
            db: Database session
        """
        self.db = db

    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text using OpenAI API.

        Args:
            text: Input text

        Returns:
            Embedding vector (list of floats)

        Raises:
            EmbeddingError: If embedding generation fails
        """
        with trace_operation("generate_embedding", {"text_length": len(text)}):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        "https://api.openai.com/v1/embeddings",
                        headers={
                            "Authorization": f"Bearer {settings.openai_api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "input": text,
                            "model": settings.embedding_model,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                    embedding = data["data"][0]["embedding"]

                    logger.info(
                        "embedding_generated",
                        text_length=len(text),
                        embedding_dim=len(embedding),
                    )

                    return embedding
            except httpx.HTTPError as e:
                raise EmbeddingError(f"Failed to generate embedding: {e}")
            except (KeyError, IndexError) as e:
                raise EmbeddingError(f"Invalid embedding response format: {e}")

    async def embed_skill_version(
        self,
        version: SkillVersion,
        custom_text: Optional[str] = None,
    ) -> List[float]:
        """
        Generate and store embedding for a skill version.

        Args:
            version: SkillVersion instance
            custom_text: Optional custom text to embed (defaults to metadata)

        Returns:
            Generated embedding vector

        Raises:
            EmbeddingError: If embedding generation fails
        """
        if custom_text:
            text = custom_text
        else:
            # Create embedding text from metadata
            metadata = version.metadata_yaml or {}
            name = metadata.get("name", "")
            description = version.description or metadata.get("description", "")
            tags = metadata.get("tags", [])
            tags_str = ", ".join(tags) if tags else ""

            # Combine fields for embedding
            text = f"{name}. {description}. Tags: {tags_str}"

        # Generate embedding
        embedding = await self.generate_embedding(text)

        # Update version with embedding
        version.embedding = embedding
        await self.db.flush()
        await self.db.refresh(version)

        logger.info(
            "skill_version_embedded",
            version_id=str(version.id),
            embedding_dim=len(embedding),
        )

        return embedding

    async def search(
        self,
        query: str,
        io_hints: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        top_k: int = 5,
        published_only: bool = True,
        min_similarity: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Search for skills using embedding similarity and filters.

        Args:
            query: Search query text
            io_hints: Optional I/O type hints (e.g., {"input_type": "text"})
            tags: Optional list of tags to filter by
            top_k: Number of results to return
            published_only: Only search published versions
            min_similarity: Minimum similarity score (0-1)

        Returns:
            List of skill version metadata dicts with similarity scores

        Raises:
            EmbeddingError: If embedding generation fails
        """
        with trace_operation(
            "search_skills",
            {"query_length": len(query), "top_k": top_k},
        ):
            # Generate query embedding
            query_embedding = await self.generate_embedding(query)

            # Build SQL query with pgvector cosine similarity
            # Note: pgvector uses <=> for cosine distance (1 - cosine_similarity)
            query_stmt = select(
                SkillVersion,
                Skill,
                text("1 - (embedding <=> :query_embedding) AS similarity")
            ).join(
                Skill, SkillVersion.skill_id == Skill.id
            ).where(
                SkillVersion.embedding.isnot(None)
            )

            # Add published filter
            if published_only:
                query_stmt = query_stmt.where(SkillVersion.is_published == True)  # noqa: E712

            # Add tag filters
            if tags:
                # Filter by tags in metadata_yaml JSONB column
                tag_conditions = []
                for tag in tags:
                    tag_conditions.append(
                        text(
                            "metadata_yaml->'tags' @> :tag"
                        ).bindparams(tag=f'["{tag}"]')
                    )
                if tag_conditions:
                    query_stmt = query_stmt.where(or_(*tag_conditions))

            # Add similarity filter
            query_stmt = query_stmt.where(
                text("1 - (embedding <=> :query_embedding) >= :min_similarity")
            )

            # Order by similarity and limit
            query_stmt = query_stmt.order_by(
                text("similarity DESC")
            ).limit(top_k)

            # Execute query with parameters
            result = await self.db.execute(
                query_stmt,
                {"query_embedding": str(query_embedding), "min_similarity": min_similarity}
            )

            rows = result.all()

            # Format results
            results = []
            for skill_version, skill, similarity in rows:
                metadata = skill_version.metadata_yaml or {}
                results.append({
                    "skill_version_id": str(skill_version.id),
                    "skill_id": str(skill.id),
                    "skill_name": skill.name,
                    "version": skill_version.version,
                    "description": skill_version.description or metadata.get("description", ""),
                    "summary": metadata.get("description", "")[:200],
                    "tags": metadata.get("tags", []),
                    "inputs": metadata.get("inputs", []),
                    "outputs": metadata.get("outputs", []),
                    "similarity": float(similarity),
                    "is_published": skill_version.is_published,
                })

            logger.info(
                "skills_searched",
                query_length=len(query),
                results_count=len(results),
                top_similarity=results[0]["similarity"] if results else None,
            )

            return results

    async def search_by_tags(
        self,
        tags: List[str],
        match_all: bool = False,
        limit: int = 20,
        published_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Search for skills by tags only (no embedding).

        Args:
            tags: List of tags to search for
            match_all: If True, match all tags; if False, match any tag
            limit: Maximum results
            published_only: Only search published versions

        Returns:
            List of skill version metadata dicts
        """
        query = select(SkillVersion, Skill).join(
            Skill, SkillVersion.skill_id == Skill.id
        )

        if published_only:
            query = query.where(SkillVersion.is_published == True)  # noqa: E712

        # Tag filtering using JSONB containment
        if tags:
            if match_all:
                # All tags must be present
                for tag in tags:
                    query = query.where(
                        text("metadata_yaml->'tags' @> :tag").bindparams(tag=f'["{tag}"]')
                    )
            else:
                # Any tag can match
                tag_conditions = []
                for tag in tags:
                    tag_conditions.append(
                        text("metadata_yaml->'tags' @> :tag").bindparams(tag=f'["{tag}"]')
                    )
                query = query.where(or_(*tag_conditions))

        query = query.order_by(SkillVersion.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        rows = result.all()

        results = []
        for skill_version, skill in rows:
            metadata = skill_version.metadata_yaml or {}
            results.append({
                "skill_version_id": str(skill_version.id),
                "skill_id": str(skill.id),
                "skill_name": skill.name,
                "version": skill_version.version,
                "description": skill_version.description or metadata.get("description", ""),
                "tags": metadata.get("tags", []),
                "inputs": metadata.get("inputs", []),
                "outputs": metadata.get("outputs", []),
                "is_published": skill_version.is_published,
            })

        logger.info("skills_searched_by_tags", tags=tags, results_count=len(results))

        return results

    async def auto_select(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        max_skills: int = 3,
    ) -> List[UUID]:
        """
        Auto-select the best skills for a query.

        Args:
            query: User query or task description
            context: Optional context (I/O hints, preferences, etc.)
            max_skills: Maximum number of skills to select

        Returns:
            List of skill version IDs, ordered by relevance

        Raises:
            EmbeddingError: If embedding generation fails
        """
        io_hints = context.get("io_hints") if context else None
        tags = context.get("tags") if context else None

        results = await self.search(
            query=query,
            io_hints=io_hints,
            tags=tags,
            top_k=max_skills,
            published_only=True,
            min_similarity=0.5,  # Require at least 50% similarity
        )

        selected_ids = [UUID(r["skill_version_id"]) for r in results]

        logger.info(
            "skills_auto_selected",
            query_length=len(query),
            selected_count=len(selected_ids),
        )

        return selected_ids
