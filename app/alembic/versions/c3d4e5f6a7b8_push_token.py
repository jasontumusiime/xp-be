"""push_token table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-08 00:25:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'push_token',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('token', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token'),
    )
    op.create_index('ix_push_token_user_id', 'push_token', ['user_id'])
    op.create_index('ix_push_token_token', 'push_token', ['token'])


def downgrade():
    op.drop_index('ix_push_token_token', table_name='push_token')
    op.drop_index('ix_push_token_user_id', table_name='push_token')
    op.drop_table('push_token')
