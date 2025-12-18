import asyncio
import json
from aiokafka import AIOKafkaConsumer
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.database.models import Post, Reaction, UserPreference
from app.ml.embeddings import embedding_model
from app.ml.recommender import recommender
from config import settings


# Kafka consumer for processing events from Java backend
class KafkaConsumerService:

    def __init__(self):
        self.consumer = None
        self.running = False

    async def start(self):
        self.consumer = AIOKafkaConsumer(
            'post.created',
            'post.updated',
            'post.deleted',
            'reaction.created',
            'reaction.updated',
            'reaction.deleted',
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=settings.KAFKA_GROUP_ID,
            auto_offset_reset=settings.KAFKA_AUTO_OFFSET_RESET,
            enable_auto_commit=True,
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )

        await self.consumer.start()
        self.running = True
        logger.info(f"Kafka consumer started (group: {settings.KAFKA_GROUP_ID})")

        # Start consuming in background
        asyncio.create_task(self._consume())

    # consume messages
    async def _consume(self):
        try:
            async for message in self.consumer:
                topic = message.topic
                key = message.key.decode('utf-8') if message.key else None
                value = message.value

                logger.info(f"📨 Received event from {topic}: {key}")

                try:
                    if topic == 'post.created':
                        await self._handle_post_created(value)
                    elif topic == 'post.updated':
                        await self._handle_post_updated(value)
                    elif topic == 'post.deleted':
                        await self._handle_post_deleted(value)
                    elif topic == 'reaction.created':
                        await self._handle_reaction_created(value)
                    elif topic == 'reaction.updated':
                        await self._handle_reaction_updated(value)
                    elif topic == 'reaction.deleted':
                        await self._handle_reaction_deleted(value)

                except Exception as e:
                    logger.error(f"Error handling {topic} event: {e}")
                    # Continue processing other messages

        except Exception as e:
            logger.error(f"Fatal error in Kafka consumer: {e}")
            self.running = False

    async def _handle_post_created(self, event: dict):
        payload = event['payload']
        post_id = payload['id']
        text = payload.get('text')

        async with async_session_factory() as session:
            # Idempotence: Check if post already exists
            result = await session.execute(
                select(Post).where(Post.id == post_id)
            )
            if result.scalar_one_or_none():
                logger.warning(f"⚠️ Post {post_id} already exists, skipping")
                return

            # Generate embedding
            embedding = None
            if text:
                emb_array = embedding_model.encode(text)
                embedding = emb_array[0] if emb_array.ndim == 2 else emb_array

            # Save to database
            post = Post(
                id=post_id,
                text=text,
                embedding=embedding,
                created_at=payload['createdAt']
            )
            session.add(post)
            await session.commit()

            logger.info(f"Created post {post_id}")

    async def _handle_post_updated(self, event: dict):
        payload = event['payload']
        post_id = payload['id']
        new_text = payload.get('text')

        async with async_session_factory() as session:
            result = await session.execute(
                select(Post).where(Post.id == post_id)
            )
            post = result.scalar_one_or_none()

            if not post:
                logger.warning(f"Post {post_id} not found for update")
                return

            post.text = new_text
            if new_text:
                emb_array = embedding_model.encode(new_text)
                post.embedding = emb_array[0] if emb_array.ndim == 2 else emb_array
            else:
                post.embedding = None

            await session.commit()
            logger.info(f"Updated post {post_id}")

    async def _handle_post_deleted(self, event: dict):
        payload = event['payload']
        post_id = payload['id']

        async with async_session_factory() as session:
            result = await session.execute(
                select(Post).where(Post.id == post_id)
            )
            post = result.scalar_one_or_none()

            if post:
                await session.delete(post)
                await session.commit()
                logger.info(f"Deleted post {post_id}")
            else:
                logger.warning(f"Post {post_id} not found for deletion")

    async def _handle_reaction_created(self, event: dict):
        payload = event['payload']
        reaction_id = payload['id']
        author_id = payload['authorId']

        async with async_session_factory() as session:
            # Idempotence: Check if reaction already exists
            result = await session.execute(
                select(Reaction).where(Reaction.id == reaction_id)
            )
            if result.scalar_one_or_none():
                logger.warning(f"⚠️ Reaction {reaction_id} already exists, skipping")
                return

            # Save reaction
            reaction = Reaction(
                id=reaction_id,
                target_id=payload['targetId'],
                author_id=author_id,
                type=payload['type'],
                created_at=payload['createdAt']
            )
            session.add(reaction)
            await session.commit()

            # Invalidate user preferences
            await recommender.invalidate_user_preference(author_id, session)

            logger.info(f"Created reaction {reaction_id}, invalidated preferences for {author_id}")

    async def _handle_reaction_updated(self, event: dict):
        payload = event['payload']
        reaction_id = payload['id']
        author_id = payload['authorId']

        async with async_session_factory() as session:
            result = await session.execute(
                select(Reaction).where(Reaction.id == reaction_id)
            )
            reaction = result.scalar_one_or_none()

            if not reaction:
                logger.warning(f"Reaction {reaction_id} not found for update")
                return

            # Update reaction type
            reaction.type = payload['type']
            await session.commit()

            # Invalidate user preferences
            await recommender.invalidate_user_preference(author_id, session)

            logger.info(f"Updated reaction {reaction_id}, invalidated preferences for {author_id}")

    async def _handle_reaction_deleted(self, event: dict):
        payload = event['payload']
        reaction_id = payload['id']
        author_id = payload['authorId']

        async with async_session_factory() as session:
            result = await session.execute(
                select(Reaction).where(Reaction.id == reaction_id)
            )
            reaction = result.scalar_one_or_none()

            if reaction:
                await session.delete(reaction)
                await session.commit()

                # Invalidate user preferences
                await recommender.invalidate_user_preference(author_id, session)

                logger.info(f"Deleted reaction {reaction_id}, invalidated preferences for {author_id}")
            else:
                logger.warning(f"Reaction {reaction_id} not found for deletion")

    async def stop(self):
        self.running = False
        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer stopped")


kafka_consumer = KafkaConsumerService()
