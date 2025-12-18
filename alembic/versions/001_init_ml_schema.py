from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.create_table(
        'posts_ml',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('embedding', Vector(384), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='public'
    )

    op.create_index(
        'idx_posts_ml_created_at',
        'posts_ml',
        ['created_at'],
        unique=False
    )

    op.execute("""
               CREATE INDEX idx_posts_ml_embedding
                   ON posts_ml
                       USING ivfflat (embedding vector_cosine_ops)
                   WITH (lists = 100)
               """)

    op.create_table(
        'reactions_ml',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('target_id', sa.BigInteger(), nullable=False),
        sa.Column('author_id', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='public'
    )

    op.create_index(
        'idx_reactions_ml_author_id',
        'reactions_ml',
        ['author_id'],
        unique=False
    )

    op.create_index(
        'idx_reactions_ml_target_id',
        'reactions_ml',
        ['target_id'],
        unique=False
    )

    op.create_table(
        'user_preferences',
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('preference_embedding', Vector(384), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('user_id'),
        schema='public'
    )

    op.execute("""
               CREATE INDEX idx_user_preferences_embedding
                   ON user_preferences
                       USING ivfflat (preference_embedding vector_cosine_ops)
                   WITH (lists = 100)
               """)


def downgrade() -> None:
    op.drop_table('user_preferences', schema='public')
    op.drop_table('reactions_ml', schema='public')
    op.drop_table('posts_ml', schema='public')

    op.execute('DROP EXTENSION IF EXISTS vector CASCADE')
