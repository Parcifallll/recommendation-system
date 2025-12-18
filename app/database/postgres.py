from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from config import settings
from app.database.models import Base
from loguru import logger

# Create async engine with connection pooling
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,              # Number of connections to keep in pool
    max_overflow=10,           # Additional connections if pool is exhausted
    pool_timeout=30,           # Seconds to wait for connection from pool
    pool_recycle=3600,         # Recycle connections after 1 hour
    pool_pre_ping=True,        # Verify connections before using them
)

# Create async session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Initialize database connection and test connectivity"""
    try:
        async with engine.connect() as conn:
            # Just test connection
            await conn.execute(text("SELECT 1"))
            logger.info("Database connection successful")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise


async def get_session() -> AsyncSession:
    """Dependency for FastAPI routes to get database session"""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def close_db():
    """Close all database connections in the pool"""
    await engine.dispose()
    logger.info("Database connections closed")