import numpy as np
from typing import Optional
from loguru import logger
from sqlalchemy import select, and_, not_
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.embeddings import embedding_model
from app.database.models import Post, Reaction, UserPreference
from app.models.post import PostResponse, PostWithEmbedding
from app.models.reaction import ReactionType, ReactionTargetType
from config import settings


class ContentBasedRecommender:
    """Content-based recommendation system using text embeddings"""

    def __init__(self):
        self.model = embedding_model

    async def get_user_preference_embedding(
            self,
            user_id: str,
            session: AsyncSession
    ) -> Optional[np.ndarray]:
        """
        Get or compute user preference embedding based on their reactions

        Args:
            user_id: User ID
            session: Database session

        Returns:
            User preference embedding or None
        """
        # Try to get cached preference embedding
        result = await session.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        user_pref = result.scalar_one_or_none()

        if user_pref and user_pref.preference_embedding:
            return np.array(user_pref.preference_embedding)

        # Compute preference embedding from reactions
        preference_embedding = await self._compute_preference_embedding(user_id, session)

        # Cache the result
        if preference_embedding is not None:
            await self._save_user_preference(user_id, preference_embedding, session)

        return preference_embedding

    async def _compute_preference_embedding(
            self,
            user_id: str,
            session: AsyncSession
    ) -> Optional[np.ndarray]:
        """
        Compute user preference embedding from liked/disliked posts

        Args:
            user_id: User ID
            session: Database session

        Returns:
            Weighted average embedding or None
        """
        # Get user's reactions to posts
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
            # Flatten nested arrays if needed
            liked_embeddings = []
            for p in liked_posts:
                emb = p.embedding
                # Check if nested [[...]]
                if isinstance(emb, list) and len(emb) > 0 and isinstance(emb[0], list):
                    emb = emb[0]  # Flatten
                liked_embeddings.append(np.array(emb))

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
            # Flatten nested arrays if needed
            disliked_embeddings = []
            for p in disliked_posts:
                emb = p.embedding
                # Check if nested [[...]]
                if isinstance(emb, list) and len(emb) > 0 and isinstance(emb[0], list):
                    emb = emb[0]  # Flatten
                disliked_embeddings.append(np.array(emb))

        if not liked_embeddings and not disliked_embeddings:
            logger.info(f"No embeddings found for user {user_id}'s reactions")
            return None

        # Compute weighted average
        # Likes contribute positively, dislikes negatively
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

        return preference_embedding

    async def _save_user_preference(
            self,
            user_id: str,
            embedding: np.ndarray,
            session: AsyncSession
    ):
        """Save user preference embedding to database"""
        result = await session.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        user_pref = result.scalar_one_or_none()

        if user_pref:
            user_pref.preference_embedding = embedding.tolist()
        else:
            user_pref = UserPreference(
                user_id=user_id,
                preference_embedding=embedding.tolist()
            )
            session.add(user_pref)

        await session.commit()
        logger.info(f"Saved preference embedding for user {user_id}")

    async def get_recommendations(
            self,
            user_id: str,
            session: AsyncSession,
            limit: int = 10,
            exclude_author_posts: bool = True
    ) -> list[PostWithEmbedding]:
        """
        Get personalized post recommendations for a user

        Args:
            user_id: User ID
            session: Database session
            limit: Number of recommendations
            exclude_author_posts: Whether to exclude user's own posts

        Returns:
            List of recommended posts with similarity scores
        """
        # Get user preference embedding
        user_embedding = await self.get_user_preference_embedding(user_id, session)

        if user_embedding is None:
            # Fallback: return popular posts
            logger.info(f"No preferences for user {user_id}, returning popular posts")
            return await self._get_popular_posts(user_id, session, limit, exclude_author_posts)

        # Get all posts (excluding user's own if requested)
        query = select(Post).where(Post.embedding.isnot(None))

        if exclude_author_posts:
            query = query.where(Post.author_id != user_id)

        # Also exclude posts user already reacted to
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

        result = await session.execute(query)
        posts = result.scalars().all()

        if not posts:
            logger.info(f"No posts available for recommendations for user {user_id}")
            return []

        # Compute similarities (flatten embeddings if needed)
        flattened_embeddings = []
        for p in posts:
            emb = p.embedding
            # Check if nested [[...]]
            if isinstance(emb, list) and len(emb) > 0 and isinstance(emb[0], list):
                emb = emb[0]  # Flatten [[...]] -> [...]
            flattened_embeddings.append(emb)

        post_embeddings = np.array(flattened_embeddings)
        similarities = self.model.compute_similarities(user_embedding, post_embeddings)

        # Create posts with scores
        posts_with_scores = []
        for post, similarity in zip(posts, similarities):
            if similarity >= settings.MIN_SIMILARITY_THRESHOLD:
                # Ensure embedding is a flat list (not nested)
                embedding = post.embedding
                if embedding and isinstance(embedding, list) and len(embedding) > 0:
                    # If it's a nested list [[...]], flatten to [...]
                    if isinstance(embedding[0], list):
                        embedding = embedding[0]

                post_dict = {
                    "id": post.id,
                    "authorId": post.author_id,
                    "text": post.text,
                    "photoUrl": post.photo_url,
                    "createdAt": post.created_at,
                    "commentsCount": post.comments_count,
                    "likesCount": post.likes_count,
                    "dislikesCount": post.dislikes_count,
                    "embedding": embedding,
                    "similarity_score": float(similarity)
                }
                posts_with_scores.append(PostWithEmbedding(**post_dict))

        # Sort by similarity and return top N
        posts_with_scores.sort(key=lambda x: x.similarity_score or 0, reverse=True)

        return posts_with_scores[:limit]

    async def _get_popular_posts(
            self,
            user_id: str,
            session: AsyncSession,
            limit: int,
            exclude_author_posts: bool
    ) -> list[PostWithEmbedding]:
        """Get popular posts as fallback when no user preferences exist"""
        query = select(Post).where(Post.embedding.isnot(None))

        if exclude_author_posts:
            query = query.where(Post.author_id != user_id)

        # Sort by likes
        query = query.order_by(Post.likes_count.desc()).limit(limit)

        result = await session.execute(query)
        posts = result.scalars().all()

        results = []
        for p in posts:
            # Ensure embedding is a flat list (not nested)
            embedding = p.embedding
            if embedding and isinstance(embedding, list) and len(embedding) > 0:
                # If it's a nested list [[...]], flatten to [...]
                if isinstance(embedding[0], list):
                    embedding = embedding[0]

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
                    embedding=embedding,
                    similarity_score=None
                )
            )

        return results


# Singleton instance
recommender = ContentBasedRecommender()