"""report_media_fields

Revision ID: c1d2e3f4a5b6
Revises: bf6e316cb322
Create Date: 2026-05-19 09:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = 'c1d2e3f4a5b6'
down_revision = 'bf6e316cb322'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('report', sa.Column('photo_url', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True))
    op.add_column('report', sa.Column('video_url', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True))
    op.add_column('report', sa.Column('voice_url', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True))
    op.add_column('report', sa.Column('document_url', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True))
    op.drop_column('report', 'media_urls')


def downgrade():
    op.add_column('report', sa.Column('media_urls', sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True))
    op.drop_column('report', 'document_url')
    op.drop_column('report', 'voice_url')
    op.drop_column('report', 'video_url')
    op.drop_column('report', 'photo_url')
