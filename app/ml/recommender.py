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
from config import settings


class ContentBasedRecommender:

    def __init__(self):
        self.model = embedding_model

    def _calculate_recency_boost(self, created_at: datetime) -> float:
        now = datetime.utcnow()
        age = now - created_at

        if age < timedelta(hours=1):
            return settings.RECENCY_BOOST_1H
        elif age < timedelta(hours=6):
            return settings.RECENCY_BOOST_6H
        elif age < timedelta(hours=24):
            return settings.RECENCY_BOOST_24H
        elif age < timedelta(days=3):
            return settings.RECENCY_BOOST_3D
        elif age < timedelta(days=7):
            return settings.RECENCY_BOOST_7D
        else:
            return settings.RECENCY_BOOST_DEFAULT

    async def _get_preference_from_redis(
            self,
            redis_client: aioredis.Redis,
            user_id: str
    ) -> Optional[np.ndarray]:
        try:
            cache_key = f"preference:{user_id}"
            cached_data = await redis_client.get(cache_key)

            if cached_data:
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
        try:
            cache_key = f"preference:{user_id}"
            embedding_bytes = embedding.astype(np.float32).tobytes()
            await redis_client.setex(
                cache_key,
                settings.PREFERENCE_CACHE_TTL,
                embedding_bytes
            )
            logger.info(f"Cached preference in Redis for user {user_id} (TTL: 24h)")
        except Exception as e:
            logger.error(f"Error caching preference in Redis: {e}")

    async def get_user_preference_embedding(
            self,
            user_id: str,
            session: AsyncSession,
            redis_client: Optional[aioredis.Redis] = None
    ) -> Optional[np.ndarray]:
        if redis_client:
            redis_preference = await self._get_preference_from_redis(redis_client, user_id)
            if redis_preference is not None:
                return redis_preference

        result = await session.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        user_pref = result.scalar_one_or_none()

        if user_pref is not None and user_pref.preference_embedding is not None:
            embedding = np.array(user_pref.preference_embedding)

            if embedding.size == 0:
                logger.warning(f"Empty embedding for user {user_id}")
                return None

            logger.info(f"Loaded preference from PostgreSQL for user {user_id}")

            if redis_client:
                await self._save_preference_to_redis(redis_client, user_id, embedding)

            return embedding

        preference_embedding = await self._compute_preference_embedding(user_id, session)

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
        preference_embedding = await self._compute_preference_embedding(user_id, session)

        # 2. Всегда сохраняем (даже если None)
        await self._save_user_preference(user_id, preference_embedding, session)

        logger.info(f"Updated preference for user {user_id} (embedding: {preference_embedding is not None})")

    async def _compute_preference_embedding(
            self,
            user_id: str,
            session: AsyncSession
    ) -> Optional[np.ndarray]:
        result = await session.execute(
            select(Reaction).where(Reaction.author_id == user_id)
        )
        reactions = result.scalars().all()

        if not reactions:
            logger.info(f"No reactions found for user {user_id}")
            return None

        liked_post_ids = [r.target_id for r in reactions if r.type == 'LIKE']
        disliked_post_ids = [r.target_id for r in reactions if r.type == 'DISLIKE']

        liked_embeddings = []
        disliked_embeddings = []

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

        preference_embedding = np.zeros(settings.EMBEDDING_DIMENSION)

        if liked_embeddings:
            liked_avg = np.mean(liked_embeddings, axis=0)
            preference_embedding += liked_avg * settings.WEIGHT_LIKE_BOOST

        if disliked_embeddings:
            disliked_avg = np.mean(disliked_embeddings, axis=0)
            preference_embedding -= disliked_avg * settings.WEIGHT_DISLIKE_PENALTY

        norm = np.linalg.norm(preference_embedding)
        if norm > 0:
            preference_embedding = preference_embedding / norm

        logger.info(f"Computed preference embedding for user {user_id}")
        return preference_embedding

    async def _save_user_preference(
            self,
            user_id: str,
            embedding: Optional[np.ndarray],  # Разрешаем None!
            session: AsyncSession
    ):
        result = await session.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        user_pref = result.scalar_one_or_none()


        embedding_list = embedding.tolist() if embedding is not None else None

        if user_pref:
            user_pref.preference_embedding = embedding_list
            user_pref.updated_at = datetime.utcnow()
        else:
            user_pref = UserPreference(
                user_id=user_id,
                preference_embedding=embedding_list,  # Может быть NULL
                updated_at=datetime.utcnow()
            )
            session.add(user_pref)

        await session.commit()
        logger.info(f"Saved preference for user {user_id} (embedding: {embedding_list is not None})")

    async def get_recommendations(
            self,
            user_id: str,
            session: AsyncSession,
            limit: int = 10,
            exclude_author_posts: bool = True,
            redis_client: Optional[aioredis.Redis] = None
    ) -> list[PostWithEmbedding]:
        user_embedding = await self.get_user_preference_embedding(user_id, session, redis_client)

        if user_embedding is None:
            logger.info(f"No preferences for user {user_id}, returning recent posts")
            return await self._get_recent_posts(user_id, session, limit, exclude_author_posts)

        query = select(Post).where(Post.embedding.isnot(None))

        if exclude_author_posts:
            query = query.where(Post.author_id != user_id)

        result = await session.execute(
            select(Reaction.target_id).where(Reaction.author_id == user_id)
        )
        reacted_post_ids = [row[0] for row in result.all()]

        if reacted_post_ids:
            query = query.where(not_(Post.id.in_(reacted_post_ids)))

        query = query.order_by(Post.created_at.desc())

        result = await session.execute(query)
        posts = result.scalars().all()

        if not posts:
            logger.info(f"No posts available for recommendations for user {user_id}")
            return []

        post_embeddings = np.array([np.array(p.embedding) for p in posts])
        similarities = self.model.compute_similarities(user_embedding, post_embeddings)

        posts_with_scores = []
        for post, similarity in zip(posts, similarities):
            if similarity >= settings.MIN_SIMILARITY_THRESHOLD:
                recency_boost = self._calculate_recency_boost(post.created_at)
                final_score = float(similarity) * recency_boost

                post_dict = {
                    "id": post.id,
                    "authorId": post.author_id,
                    "text": post.text,
                    "photoUrl": post.photo_url,
                    "createdAt": post.created_at,
                    "commentsCount": 0,
                    "likesCount": 0,
                    "dislikesCount": 0,
                    "embedding": list(post.embedding),
                    "similarity_score": final_score
                }
                posts_with_scores.append(PostWithEmbedding(**post_dict))

        posts_with_scores.sort(key=lambda x: x.similarity_score or 0, reverse=True)

        logger.info(f"Returning {len(posts_with_scores[:limit])} recommendations for user {user_id}")
        return posts_with_scores[:limit]

    async def _get_recent_posts(
            self,
            user_id: str,
            session: AsyncSession,
            limit: int,
            exclude_author_posts: bool
    ) -> list[PostWithEmbedding]:
        query = select(Post).where(Post.embedding.isnot(None))

        if exclude_author_posts:
            query = query.where(Post.author_id != user_id)

        query = query.order_by(Post.created_at.desc()).limit(limit)

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
                    commentsCount=0,
                    likesCount=0,
                    dislikesCount=0,
                    embedding=list(p.embedding),
                    similarity_score=None
                )
            )

        return results


recommender = ContentBasedRecommender()