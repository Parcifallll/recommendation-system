from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text  # ← ДОБАВИТЬ!
from config import settings
from app.database.models import Base
from loguru import logger

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    poolclass=NullPool,
)

# Create async session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Initialize database tables"""

    # 1. CREATE EXTENSION в отдельной транзакции
    async with engine.connect() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.commit()
        logger.info("pgvector extension enabled")

    # 2. CREATE TABLES в новой транзакции
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")

        # 3. CREATE INDEXES
        await conn.execute(text("""
                                CREATE INDEX IF NOT EXISTS posts_embedding_idx
                                    ON posts USING ivfflat (embedding vector_cosine_ops)
                                    WITH (lists = 100)
                                """))
        logger.info("Created IVFFlat index on posts.embedding")

        await conn.execute(text("""
                                CREATE INDEX IF NOT EXISTS user_preferences_embedding_idx
                                    ON user_preferences USING ivfflat (preference_embedding vector_cosine_ops)
                                    WITH (lists = 100)
                                """))
        logger.info("Created IVFFlat index on user_preferences.preference_embedding")

        await conn.execute(text("""
                                CREATE INDEX IF NOT EXISTS posts_created_at_idx
                                    ON posts (created_at DESC)
                                """))
        logger.info("Created index on posts.created_at")


async def get_session() -> AsyncSession:
    """Dependency for getting database session"""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def close_db():
    """Close database connections"""
    await engine.dispose()
    logger.info("Database connections closed")