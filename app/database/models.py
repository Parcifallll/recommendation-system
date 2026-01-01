from datetime import datetime
from sqlalchemy import Column, BigInteger, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class Post(Base):
    __tablename__ = "posts_ml"

    id = Column(BigInteger, primary_key=True)
    author_id = Column(String(255), nullable=False, index=True)
    text = Column(Text, nullable=True)
    photo_url = Column(String(500), nullable=True)
    embedding = Column(Vector(384), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<Post(id={self.id})>"


class Reaction(Base):
    __tablename__ = "reactions_ml"

    id = Column(BigInteger, primary_key=True)
    target_id = Column(BigInteger, nullable=False, index=True)
    author_id = Column(String(255), nullable=False, index=True)
    type = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Reaction(id={self.id}, type={self.type})>"


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id = Column(String(255), primary_key=True, index=True)
    preference_embedding = Column(Vector(384), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<UserPreference(user_id={self.user_id})>"