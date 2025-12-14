from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


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
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: str
    REDIS_DB: int
    CACHE_TTL: int

    # ML Model
    MODEL_NAME: str
    EMBEDDING_DIMENSION: int
    TOP_N_RECOMMENDATIONS: int
    MIN_SIMILARITY_THRESHOLD: float

    # Weights for recommendation scoring
    WEIGHT_CONTENT_SIMILARITY: float
    WEIGHT_LIKE_BOOST: float
    WEIGHT_DISLIKE_PENALTY: float

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
