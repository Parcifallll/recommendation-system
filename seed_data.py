"""
Seed test data into the database
Run: python seed_data.py
"""
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select
from app.database.postgres import async_session_factory, init_db
from app.database.models import Post, Reaction
from app.ml.embeddings import embedding_model
from loguru import logger


# Sample posts with different topics
SAMPLE_POSTS = [
    {"id": 1, "author_id": "alice", "text": "Just finished reading a great book about machine learning and AI. The future is exciting!"},
    {"id": 2, "author_id": "bob", "text": "Amazing sunset today! Nature is truly beautiful. 🌅"},
    {"id": 3, "author_id": "charlie", "text": "New recipe for chocolate cake turned out perfect! Baking is my passion."},
    {"id": 4, "author_id": "alice", "text": "Exploring neural networks and deep learning architectures. Anyone else into AI research?"},
    {"id": 5, "author_id": "diana", "text": "Hiking in the mountains this weekend. Fresh air and beautiful views!"},
    {"id": 6, "author_id": "bob", "text": "Photography tips: golden hour is the best time for outdoor shots."},
    {"id": 7, "author_id": "charlie", "text": "Tried making sushi at home. It's harder than it looks but so rewarding!"},
    {"id": 8, "author_id": "eve", "text": "Data science project on climate change predictions. Fascinating insights!"},
    {"id": 9, "author_id": "frank", "text": "Beach day! Swimming and volleyball with friends. Perfect summer day."},
    {"id": 10, "author_id": "diana", "text": "Camping under the stars. Nothing beats sleeping in nature."},
    {"id": 11, "author_id": "eve", "text": "Working on a computer vision project using PyTorch. Anyone familiar with CNNs?"},
    {"id": 12, "author_id": "charlie", "text": "Italian pasta carbonara - authentic recipe from my grandmother."}
]

# Sample reactions (user123 likes AI/tech and nature posts)
SAMPLE_REACTIONS = [
    {"id": 1, "target_type": "POST", "target_id": 1, "author_id": "user123", "type": "LIKE"},
    {"id": 2, "target_type": "POST", "target_id": 4, "author_id": "user123", "type": "LIKE"},
    {"id": 3, "target_type": "POST", "target_id": 8, "author_id": "user123", "type": "LIKE"},
    {"id": 4, "target_type": "POST", "target_id": 11, "author_id": "user123", "type": "LIKE"},
    {"id": 5, "target_type": "POST", "target_id": 5, "author_id": "user123", "type": "LIKE"},
    {"id": 6, "target_type": "POST", "target_id": 10, "author_id": "user123", "type": "LIKE"},
    {"id": 7, "target_type": "POST", "target_id": 3, "author_id": "user123", "type": "DISLIKE"},
    {"id": 8, "target_type": "POST", "target_id": 7, "author_id": "user123", "type": "DISLIKE"},
    {"id": 9, "target_type": "POST", "target_id": 12, "author_id": "user123", "type": "DISLIKE"}
]


async def seed_data():
    """Seed test data into database"""
    logger.info("Initializing database...")

    # Initialize DB (creates extension, tables, indexes)
    await init_db()

    async with async_session_factory() as session:
        # Check if data already exists
        result = await session.execute(select(Post))
        existing_posts = result.scalars().all()

        if existing_posts:
            logger.warning("⚠️  Database already contains posts. Skipping seed.")
            return

        logger.info("Creating sample posts with embeddings...")

        # Create posts with embeddings
        for post_data in SAMPLE_POSTS:
            embedding = None
            if post_data['text']:
                # Generate embedding
                embedding_array = embedding_model.encode(post_data['text'])

                # Convert 2D to 1D if needed (pgvector needs 1D array)
                if embedding_array.ndim == 2:
                    embedding = embedding_array[0]  # (1, 384) -> (384,)
                else:
                    embedding = embedding_array  # Already (384,)

            post = Post(
                id=post_data['id'],
                author_id=post_data['author_id'],
                text=post_data['text'],
                created_at=datetime.utcnow() - timedelta(days=len(SAMPLE_POSTS) - post_data['id']),
                embedding=embedding,  # 1D numpy array for pgvector
                likes_count=0,
                dislikes_count=0,
                comments_count=0
            )
            session.add(post)

        logger.info(f"✅ Created {len(SAMPLE_POSTS)} posts with embeddings")

        # Create reactions
        logger.info("Creating sample reactions...")
        for reaction_data in SAMPLE_REACTIONS:
            reaction = Reaction(
                id=reaction_data['id'],
                target_type=reaction_data['target_type'],
                target_id=reaction_data['target_id'],
                author_id=reaction_data['author_id'],
                type=reaction_data['type'],
                created_at=datetime.utcnow() - timedelta(hours=len(SAMPLE_REACTIONS) - reaction_data['id'])
            )
            session.add(reaction)

        logger.info(f"✅ Created {len(SAMPLE_REACTIONS)} reactions")

        # Commit all changes
        await session.commit()

        logger.info("\n🎉 Database seeded successfully!")
        logger.info("\n📊 Summary:")
        logger.info(f"  • {len(SAMPLE_POSTS)} posts created")
        logger.info(f"  • {len(SAMPLE_REACTIONS)} reactions created")
        logger.info(f"  • User 'user123' likes: AI, data science, nature posts")
        logger.info(f"  • User 'user123' dislikes: cooking posts")
        logger.info("\n💡 Test recommendations:")
        logger.info("   POST http://localhost:8001/recommendations/")
        logger.info('   {"userId": "user123", "limit": 5}')


if __name__ == "__main__":
    asyncio.run(seed_data())