import json

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
    """Service for handling recommendation logic"""

    def __init__(self):
        self.recommender = recommender
        self.embedding_model = embedding_model
        self.redis_client: aioredis.Redis | None = None

    async def init_redis(self):
        """Initialize Redis connection"""
        try:
            # Build Redis URL with password
            redis_url = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

            self.redis_client = await aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info("Redis connection established")
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

        Args:
            request: Recommendation request
            session: Database session

        Returns:
            Recommendation response
        """
        # Check cache first
        cached = await self._get_cached_recommendations(request.user_id)
        if cached:
            logger.info(f"Returning cached recommendations for user {request.user_id}")
            return cached

        # Get recommendations from ML model
        recommended_posts = await self.recommender.get_recommendations(
            user_id=request.user_id,
            session=session,
            limit=request.limit,
            exclude_author_posts=request.exclude_author_posts
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

        # Cache the results
        await self._cache_recommendations(request.user_id, response)

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
            embedding = embedding_array.tolist()

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
        Create a new reaction and invalidate user's recommendation cache

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

        logger.info(f"Created reaction {reaction.id} by user {reaction.author_id}")

        # Invalidate cache for this user
        await self._invalidate_user_cache(reaction_data.author_id)

    async def _get_cached_recommendations(
            self,
            user_id: str
    ) -> RecommendationResponse | None:
        """Get cached recommendations from Redis"""
        if not self.redis_client:
            return None

        try:
            cache_key = f"recommendations:{user_id}"
            cached_data = await self.redis_client.get(cache_key)

            if cached_data:
                data = json.loads(cached_data)
                return RecommendationResponse(**data)
        except Exception as e:
            logger.error(f"Error getting cached recommendations: {e}")

        return None

    async def _cache_recommendations(
            self,
            user_id: str,
            response: RecommendationResponse
    ):
        """Cache recommendations in Redis"""
        if not self.redis_client:
            return

        try:
            cache_key = f"recommendations:{user_id}"
            # Convert to dict for JSON serialization
            data = response.model_dump(mode='json')
            await self.redis_client.setex(
                cache_key,
                settings.CACHE_TTL,
                json.dumps(data)
            )
            logger.info(f"Cached recommendations for user {user_id}")
        except Exception as e:
            logger.error(f"Error caching recommendations: {e}")

    async def _invalidate_user_cache(self, user_id: str):
        """Invalidate cached recommendations for a user"""
        if not self.redis_client:
            return

        try:
            cache_key = f"recommendations:{user_id}"
            await self.redis_client.delete(cache_key)
            logger.info(f"Invalidated cache for user {user_id}")
        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")


# Singleton instance
recommendation_service = RecommendationService()
