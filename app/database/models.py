from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class Post(Base):
    """SQLAlchemy model for posts"""
    __tablename__ = "posts"

    id = Column(BigInteger, primary_key=True, index=True)
    author_id = Column(String, nullable=False, index=True)
    text = Column(Text, nullable=True)
    photo_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Cached counters
    comments_count = Column(BigInteger, default=0)
    likes_count = Column(BigInteger, default=0)
    dislikes_count = Column(BigInteger, default=0)

    # Text embedding with pgvector (384 dimensions)
    embedding = Column(Vector(384), nullable=True)

    def __repr__(self):
        return f"<Post(id={self.id}, author_id={self.author_id})>"


class Reaction(Base):
    """SQLAlchemy model for reactions"""
    __tablename__ = "reactions"

    id = Column(BigInteger, primary_key=True, index=True)
    target_type = Column(String, nullable=False)
    target_id = Column(BigInteger, nullable=False, index=True)
    author_id = Column(String, nullable=False, index=True)
    type = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Reaction(id={self.id}, type={self.type}, target_id={self.target_id})>"


class UserPreference(Base):
    """SQLAlchemy model for user preferences"""
    __tablename__ = "user_preferences"

    user_id = Column(String, primary_key=True, index=True)
    # Preference embedding with pgvector (384 dimensions)
    preference_embedding = Column(Vector(384), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<UserPreference(user_id={self.user_id})>"