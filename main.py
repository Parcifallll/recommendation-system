from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger

from app.kafka.consumer import kafka_consumer
from app.api import recommendations
from app.services.recommendation_service import recommendation_service
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application...")

    try:
        # Initialize Redis connection
        await recommendation_service.init_redis()
        logger.info("Redis initialized")

        # Start Kafka consumer in background
        await kafka_consumer.start()
        logger.info("Kafka consumer started")

    except Exception as e:
        logger.error(f"Failed to start services: {e}")
        raise

    yield

    logger.info("Shutting down application...")

    await kafka_consumer.stop()
    logger.info("Kafka consumer stopped")

    await recommendation_service.close_redis()
    logger.info("Redis connection closed")

    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# Include api routes
app.include_router(recommendations.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "kafka_consumer_running": kafka_consumer.running
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )