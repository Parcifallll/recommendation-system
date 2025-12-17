import json
import numpy as np

import redis.asyncio as aioredis
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Post, Reaction
from app.ml.embeddings import embedding_model
from app.ml.recommender import recommender
from app.models.post import PostResponse, PostCreate
from app.models.reaction import ReactionCreate
from app.models.user import RecommendationRequest, RecommendationResponse
from config import settings


class RecommendationService:
    """Service for handling recommendation logic with Redis caching"""

    def __init__(self):
        self.recommender = recommender
        self.embedding_model = embedding_model
        self.redis_client: aioredis.Redis | None = None

    async def init_redis(self):
        """Initialize Redis connection"""
        try:
            redis_url = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

            self.redis_client = await aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=False  # For binary data (numpy arrays)
            )
            logger.info("✅ Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None

    async def close_redis(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")

    async def get_recommendations(
            self,
            request: RecommendationRequest,
            session: AsyncSession
    ) -> RecommendationResponse:
        """
        Get personalized recommendations for a user

        Flow:
        1. Recommender checks Redis for cached preference
        2. If not in Redis, checks PostgreSQL
        3. If not in PostgreSQL, computes from reactions
        4. Gets ALL posts (always fresh from PostgreSQL!)
        5. Ranks with similarity × recency_boost
        6. Returns top N

        NOTE: We do NOT cache recommendation results!
        Only preference embeddings are cached in Redis.
        Posts are ALWAYS loaded fresh from PostgreSQL.

        Args:
            request: Recommendation request
            session: Database session

        Returns:
            Recommendation response
        """
        # Pass redis_client to recommender for preference caching
        recommended_posts = await self.recommender.get_recommendations(
            user_id=request.user_id,
            session=session,
            limit=request.limit,
            exclude_author_posts=request.exclude_author_posts,
            redis_client=self.redis_client  # Pass Redis client
        )

        # Convert to response format
        post_responses = [
            PostResponse(
                id=p.id,
                authorId=p.author_id,
                text=p.text,
                photoUrl=p.photo_url,
                createdAt=p.created_at,
                commentsCount=p.comments_count,
                likesCount=p.likes_count,
                dislikesCount=p.dislikes_count
            )
            for p in recommended_posts
        ]

        response = RecommendationResponse(
            user_id=request.user_id,
            recommendations=post_responses,
            total_count=len(post_responses)
        )

        return response

    async def create_post(self, post_data: PostCreate, session: AsyncSession) -> PostResponse:
        """
        Create a new post and generate its embedding

        Args:
            post_data: Post creation data
            session: Database session

        Returns:
            Created post
        """
        # Generate embedding for post text
        embedding = None
        if post_data.text:
            embedding_array = self.embedding_model.encode(post_data.text)

            # Convert 2D to 1D if needed (pgvector needs 1D)
            if embedding_array.ndim == 2:
                embedding = embedding_array[0]
            else:
                embedding = embedding_array

        # Create post in database
        post = Post(
            id=post_data.id,
            author_id=post_data.author_id,
            text=post_data.text,
            photo_url=post_data.photo_url,
            created_at=post_data.created_at,
            embedding=embedding
        )

        session.add(post)
        await session.commit()
        await session.refresh(post)

        logger.info(f"Created post {post.id} with embedding")

        return PostResponse(
            id=post.id,
            authorId=post.author_id,
            text=post.text,
            photoUrl=post.photo_url,
            createdAt=post.created_at,
            commentsCount=post.comments_count,
            likesCount=post.likes_count,
            dislikesCount=post.dislikes_count
        )

    async def create_reaction(
            self,
            reaction_data: ReactionCreate,
            session: AsyncSession
    ):
        """
        Create a new reaction and invalidate user's caches

        Flow:
        1. Save reaction to PostgreSQL
        2. Delete preference from PostgreSQL (invalidate)
        3. Delete preference from Redis (invalidate)

        Next recommendation request will recompute preference!

        Args:
            reaction_data: Reaction creation data
            session: Database session
        """
        # Create reaction in database
        reaction = Reaction(
            id=reaction_data.id,
            target_type=reaction_data.target_type.value,
            target_id=reaction_data.target_id,
            author_id=reaction_data.author_id,
            type=reaction_data.type.value,
            created_at=reaction_data.created_at
        )

        session.add(reaction)
        await session.commit()

        logger.info(f"Created reaction {reaction.id} by user {reaction_data.author_id}")

        # Invalidate BOTH caches
        # 1. Delete from PostgreSQL
        await self.recommender.invalidate_user_preference(reaction_data.author_id, session)

        # 2. Delete from Redis
        await self._invalidate_preference_redis(reaction_data.author_id)

    async def _invalidate_preference_redis(self, user_id: str):
        """Invalidate cached preference in Redis"""
        if not self.redis_client:
            return

        try:
            cache_key = f"preference:{user_id}"
            await self.redis_client.delete(cache_key)
            logger.info(f"Invalidated preference in Redis for user {user_id}")
        except Exception as e:
            logger.error(f"Error invalidating preference in Redis: {e}")


# Singleton instance
recommendation_service = RecommendationService()