from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger, ARRAY, Float
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Post(Base):
    """SQLAlchemy model for posts"""
    __tablename__ = "posts"
    
    id = Column(BigInteger, primary_key=True, index=True)
    author_id = Column(String, nullable=False, index=True)
    text = Column(Text, nullable=True)
    photo_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Cached counters
    comments_count = Column(BigInteger, default=0)
    likes_count = Column(BigInteger, default=0)
    dislikes_count = Column(BigInteger, default=0)
    
    # Text embedding (384 dimensions for all-MiniLM-L6-v2)
    embedding = Column(ARRAY(Float), nullable=True)
    
    def __repr__(self):
        return f"<Post(id={self.id}, author_id={self.author_id})>"


class Reaction(Base):
    """SQLAlchemy model for reactions"""
    __tablename__ = "reactions"
    
    id = Column(BigInteger, primary_key=True, index=True)
    target_type = Column(String, nullable=False)  # POST or COMMENT
    target_id = Column(BigInteger, nullable=False, index=True)
    author_id = Column(String, nullable=False, index=True)
    type = Column(String, nullable=False)  # LIKE or DISLIKE
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<Reaction(id={self.id}, type={self.type}, target_id={self.target_id})>"


class UserPreference(Base):
    """SQLAlchemy model for user preferences"""
    __tablename__ = "user_preferences"
    
    user_id = Column(String, primary_key=True, index=True)
    preference_embedding = Column(ARRAY(Float), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<UserPreference(user_id={self.user_id})>"
