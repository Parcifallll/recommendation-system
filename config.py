from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    APP_NAME: str
    APP_VERSION: str
    DEBUG: bool
    HOST: str
    PORT: int

    # PostgreSQL
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    @property
    def DATABASE_URL(self) -> str:
        """Async database URL for SQLAlchemy (asyncpg driver)"""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Sync database URL for Alembic migrations (psycopg2 driver)"""
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: str
    REDIS_DB: int
    PREFERENCE_CACHE_TTL: int = 86400

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_GROUP_ID: str = "python-ml-service"
    KAFKA_AUTO_OFFSET_RESET: str = "earliest"  # or latest

    # ML Model
    MODEL_NAME: str
    EMBEDDING_DIMENSION: int
    TOP_N_RECOMMENDATIONS: int
    MIN_SIMILARITY_THRESHOLD: float

    # Weights for recommendation scoring
    WEIGHT_CONTENT_SIMILARITY: float
    WEIGHT_LIKE_BOOST: float
    WEIGHT_DISLIKE_PENALTY: float

    # Recency boost settings
    RECENCY_BOOST_1H: float = 2.0  # < 1 hour
    RECENCY_BOOST_6H: float = 1.8  # 1-6 hours
    RECENCY_BOOST_24H: float = 1.5  # 6- 24 hours
    RECENCY_BOOST_3D: float = 1.3  # 1-3 days
    RECENCY_BOOST_7D: float = 1.1  #3-7 days
    RECENCY_BOOST_DEFAULT: float = 1.0  #> 7 days

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()