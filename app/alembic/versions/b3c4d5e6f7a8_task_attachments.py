"""add attachment fields to task

Revision ID: b3c4d5e6f7a8
Revises: ee1a2b3c4d5f
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = 'b3c4d5e6f7a8'
down_revision = 'ee1a2b3c4d5f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('task', sa.Column('photo_url', sa.String(length=500), nullable=True))
    op.add_column('task', sa.Column('video_url', sa.String(length=500), nullable=True))
    op.add_column('task', sa.Column('voice_url', sa.String(length=500), nullable=True))
    op.add_column('task', sa.Column('document_url', sa.String(length=500), nullable=True))


def downgrade():
    op.drop_column('task', 'document_url')
    op.drop_column('task', 'voice_url')
    op.drop_column('task', 'video_url')
    op.drop_column('task', 'photo_url')
