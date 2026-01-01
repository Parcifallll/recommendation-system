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

    def __init__(self):
        self.recommender = recommender
        self.embedding_model = embedding_model
        self.redis_client: aioredis.Redis | None = None

    async def init_redis(self):
        try:
            redis_url = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

            self.redis_client = await aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=False
            )
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None

    async def close_redis(self):
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")

    async def get_recommendations(
            self,
            request: RecommendationRequest,
            session: AsyncSession
    ) -> RecommendationResponse:

        recommended_posts = await self.recommender.get_recommendations(
            user_id=request.user_id,
            session=session,
            limit=request.limit,
            exclude_author_posts=request.exclude_author_posts,
            redis_client=self.redis_client
        )

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
        embedding = None
        if post_data.text:
            embedding_array = self.embedding_model.encode(post_data.text)

            if embedding_array.ndim == 2:
                embedding = embedding_array[0]
            else:
                embedding = embedding_array

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
            commentsCount=0,
            likesCount=0,
            dislikesCount=0
        )

    async def create_reaction(
            self,
            reaction_data: ReactionCreate,
            session: AsyncSession
    ):
        reaction = Reaction(
            id=reaction_data.id,
            target_id=reaction_data.target_id,
            author_id=reaction_data.author_id,
            type=reaction_data.type.value,
            created_at=reaction_data.created_at
        )

        session.add(reaction)
        await session.commit()

        logger.info(f"Created reaction {reaction.id} by user {reaction_data.author_id}")

        await self.recommender.invalidate_user_preference(
            reaction_data.author_id,
            session,
            self.redis_client
        )

    async def invalidate_preference_redis(self, user_id: str):
        if not self.redis_client:
            return

        try:
            cache_key = f"preference:{user_id}"
            await self.redis_client.delete(cache_key)
            logger.info(f"Invalidated preference in Redis for user {user_id}")
        except Exception as e:
            logger.error(f"Error invalidating preference in Redis: {e}")


recommendation_service = RecommendationService()