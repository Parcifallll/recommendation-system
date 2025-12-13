from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
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
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")


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
