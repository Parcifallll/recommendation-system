from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import redis.asyncio as aioredis
from loguru import logger
from sqlalchemy import select, and_, not_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Post, Reaction, UserPreference
from app.ml.embeddings import embedding_model
from app.models.post import PostWithEmbedding
from app.models.reaction import ReactionType, ReactionTargetType
from config import settings


class ContentBasedRecommender:

    def __init__(self):
        self.model = embedding_model

    def _calculate_recency_boost(self, created_at: datetime) -> float:

        now = datetime.utcnow()
        age = now - created_at

        if age < timedelta(hours=1):
            return settings.RECENCY_BOOST_1H  # 2.0
        elif age < timedelta(hours=6):
            return settings.RECENCY_BOOST_6H  # 1.8
        elif age < timedelta(hours=24):
            return settings.RECENCY_BOOST_24H  # 1.5
        elif age < timedelta(days=3):
            return settings.RECENCY_BOOST_3D  # 1.3
        elif age < timedelta(days=7):
            return settings.RECENCY_BOOST_7D  # 1.1
        else:
            return settings.RECENCY_BOOST_DEFAULT  # 1.0

    async def _get_preference_from_redis(
            self,
            redis_client: aioredis.Redis,
            user_id: str
    ) -> Optional[np.ndarray]:

        try:
            cache_key = f"preference:{user_id}"
            cached_data = await redis_client.get(cache_key)

            if cached_data:
                # Deserialize numpy array from bytes
                preference = np.frombuffer(cached_data, dtype=np.float32)
                logger.info(f"Loaded preference from Redis for user {user_id}")
                return preference
        except Exception as e:
            logger.error(f"Error getting preference from Redis: {e}")

        return None

    async def _save_preference_to_redis(
            self,
            redis_client: aioredis.Redis,
            user_id: str,
            embedding: np.ndarray
    ):
        """Save user preference embedding to Redis cache"""
        try:
            cache_key = f"preference:{user_id}"
            # Serialize numpy array to bytes
            embedding_bytes = embedding.astype(np.float32).tobytes()
            await redis_client.setex(
                cache_key,
                settings.PREFERENCE_CACHE_TTL,  # 24 hours
                embedding_bytes
            )
            logger.info(f" Cached preference in Redis for user {user_id} (TTL: 24h)")
        except Exception as e:
            logger.error(f"Error caching preference in Redis: {e}")

    async def get_user_preference_embedding(
            self,
            user_id: str,
            session: AsyncSession,
            redis_client: Optional[aioredis.Redis] = None
    ) -> Optional[np.ndarray]:

        # Try Redis cache (fastest)
        if redis_client:
            redis_preference = await self._get_preference_from_redis(redis_client, user_id)
            if redis_preference is not None:
                return redis_preference

        # Try PostgreSQL
        result = await session.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        user_pref = result.scalar_one_or_none()

        # Check if preference exists (avoid array boolean comparison)
        if user_pref is not None and user_pref.preference_embedding is not None:
            # Convert pgvector to numpy array
            embedding = np.array(user_pref.preference_embedding)

            # Validate that embedding is not empty
            if embedding.size == 0:
                logger.warning(f"Empty embedding for user {user_id}")
                return None

            logger.info(f"Loaded preference from PostgreSQL for user {user_id}")

            # Save to Redis for next time
            if redis_client:
                await self._save_preference_to_redis(redis_client, user_id, embedding)

            return embedding

        # Compute preference embedding from reactions
        preference_embedding = await self._compute_preference_embedding(user_id, session)

        # Cache the result in both PostgreSQL and Redis
        if preference_embedding is not None:
            await self._save_user_preference(user_id, preference_embedding, session)

            if redis_client:
                await self._save_preference_to_redis(redis_client, user_id, preference_embedding)

        return preference_embedding

    async def invalidate_user_preference(
            self,
            user_id: str,
            session: AsyncSession
    ):

        await session.execute(
            text("DELETE FROM user_preferences WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        await session.commit()
        logger.info(f"Invalidated preference in PostgreSQL for user {user_id}")

    async def _compute_preference_embedding(
            self,
            user_id: str,
            session: AsyncSession
    ) -> Optional[np.ndarray]:

        # пet user's reactions to posts
        result = await session.execute(
            select(Reaction).where(
                and_(
                    Reaction.author_id == user_id,
                    Reaction.target_type == ReactionTargetType.POST.value
                )
            )
        )
        reactions = result.scalars().all()

        if not reactions:
            logger.info(f"No reactions found for user {user_id}")
            return None

        # Separate liked and disliked posts
        liked_post_ids = [r.target_id for r in reactions if r.type == ReactionType.LIKE.value]
        disliked_post_ids = [r.target_id for r in reactions if r.type == ReactionType.DISLIKE.value]

        liked_embeddings = []
        disliked_embeddings = []

        # Get embeddings for liked posts
        if liked_post_ids:
            result = await session.execute(
                select(Post).where(
                    and_(
                        Post.id.in_(liked_post_ids),
                        Post.embedding.isnot(None)
                    )
                )
            )
            liked_posts = result.scalars().all()
            liked_embeddings = [np.array(p.embedding) for p in liked_posts]

        # Get embeddings for disliked posts
        if disliked_post_ids:
            result = await session.execute(
                select(Post).where(
                    and_(
                        Post.id.in_(disliked_post_ids),
                        Post.embedding.isnot(None)
                    )
                )
            )
            disliked_posts = result.scalars().all()
            disliked_embeddings = [np.array(p.embedding) for p in disliked_posts]

        if not liked_embeddings and not disliked_embeddings:
            logger.info(f"No embeddings found for user {user_id}'s reactions")
            return None

        # Compute weighted average
        preference_embedding = np.zeros(settings.EMBEDDING_DIMENSION)

        if liked_embeddings:
            liked_avg = np.mean(liked_embeddings, axis=0)
            preference_embedding += liked_avg * settings.WEIGHT_LIKE_BOOST

        if disliked_embeddings:
            disliked_avg = np.mean(disliked_embeddings, axis=0)
            preference_embedding -= disliked_avg * settings.WEIGHT_DISLIKE_PENALTY

        # Normalize
        norm = np.linalg.norm(preference_embedding)
        if norm > 0:
            preference_embedding = preference_embedding / norm

        logger.info(f"Computed preference embedding for user {user_id}")
        return preference_embedding

    async def _save_user_preference(
            self,
            user_id: str,
            embedding: np.ndarray,
            session: AsyncSession
    ):
        result = await session.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        user_pref = result.scalar_one_or_none()

        embedding_list = embedding.tolist()

        if user_pref:
            user_pref.preference_embedding = embedding_list
            user_pref.updated_at = datetime.utcnow()
        else:
            user_pref = UserPreference(
                user_id=user_id,
                preference_embedding=embedding_list,
                updated_at=datetime.utcnow()
            )
            session.add(user_pref)

        await session.commit()
        logger.info(f"Saved preference to PostgreSQL for user {user_id}")

    async def get_recommendations(
            self,
            user_id: str,
            session: AsyncSession,
            limit: int = 10,
            exclude_author_posts: bool = True,
            redis_client: Optional[aioredis.Redis] = None
    ) -> list[PostWithEmbedding]:
        # Get user preference embedding (checks Redis → PostgreSQL → Compute)
        user_embedding = await self.get_user_preference_embedding(user_id, session, redis_client)

        if user_embedding is None:
            # Fallback: return recent popular posts
            logger.info(f"No preferences for user {user_id}, returning recent popular posts")
            return await self._get_recent_popular_posts(user_id, session, limit, exclude_author_posts)

        # Get ALL posts (ALWAYS fresh from PostgreSQL!)
        query = select(Post).where(Post.embedding.isnot(None))

        if exclude_author_posts:
            query = query.where(Post.author_id != user_id)

        # Exclude posts user already reacted to
        result = await session.execute(
            select(Reaction.target_id).where(
                and_(
                    Reaction.author_id == user_id,
                    Reaction.target_type == ReactionTargetType.POST.value
                )
            )
        )
        reacted_post_ids = [row[0] for row in result.all()]

        if reacted_post_ids:
            query = query.where(not_(Post.id.in_(reacted_post_ids)))

        # Order by created_at DESC to get newest first
        query = query.order_by(Post.created_at.desc())

        result = await session.execute(query)
        posts = result.scalars().all()

        if not posts:
            logger.info(f"No posts available for recommendations for user {user_id}")
            return []

        # Compute similarities
        post_embeddings = np.array([np.array(p.embedding) for p in posts])
        similarities = self.model.compute_similarities(user_embedding, post_embeddings)

        # Create posts with scores (similarity × recency_boost)
        posts_with_scores = []
        for post, similarity in zip(posts, similarities):
            if similarity >= settings.MIN_SIMILARITY_THRESHOLD:
                # Calculate recency boost
                recency_boost = self._calculate_recency_boost(post.created_at)

                # Final score = similarity × recency_boost
                final_score = float(similarity) * recency_boost

                post_dict = {
                    "id": post.id,
                    "authorId": post.author_id,
                    "text": post.text,
                    "photoUrl": post.photo_url,
                    "createdAt": post.created_at,
                    "commentsCount": post.comments_count,
                    "likesCount": post.likes_count,
                    "dislikesCount": post.dislikes_count,
                    "embedding": list(post.embedding),
                    "similarity_score": final_score  # Final score with recency boost!
                }
                posts_with_scores.append(PostWithEmbedding(**post_dict))

        # Sort by final score (similarity × recency) - highest first
        posts_with_scores.sort(key=lambda x: x.similarity_score or 0, reverse=True)

        logger.info(f"Returning {len(posts_with_scores[:limit])} recommendations for user {user_id}")
        return posts_with_scores[:limit]

    async def _get_recent_popular_posts(
            self,
            user_id: str,
            session: AsyncSession,
            limit: int,
            exclude_author_posts: bool
    ) -> list[PostWithEmbedding]:
        """Get recent popular posts as fallback when no user preferences exist"""
        query = select(Post).where(Post.embedding.isnot(None))

        if exclude_author_posts:
            query = query.where(Post.author_id != user_id)

        # Sort by likes first, then recency
        query = query.order_by(
            Post.likes_count.desc(),
            Post.created_at.desc()
        ).limit(limit)

        result = await session.execute(query)
        posts = result.scalars().all()

        results = []
        for p in posts:
            results.append(
                PostWithEmbedding(
                    id=p.id,
                    authorId=p.author_id,
                    text=p.text,
                    photoUrl=p.photo_url,
                    createdAt=p.created_at,
                    commentsCount=p.comments_count,
                    likesCount=p.likes_count,
                    dislikesCount=p.dislikes_count,
                    embedding=list(p.embedding),
                    similarity_score=None
                )
            )

        return results

recommender = ContentBasedRecommender()