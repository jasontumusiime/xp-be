"""user phone_number unique index and not-null

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-08 00:35:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    # Set a placeholder for any existing NULL phone numbers before adding constraint
    op.execute("UPDATE \"user\" SET phone_number = '+256700000000' WHERE phone_number IS NULL")
    op.alter_column('user', 'phone_number', nullable=False)
    op.create_unique_constraint('uq_user_phone_number', 'user', ['phone_number'])
    op.create_index('ix_user_phone_number', 'user', ['phone_number'])


def downgrade():
    op.drop_index('ix_user_phone_number', table_name='user')
    op.drop_constraint('uq_user_phone_number', 'user', type_='unique')
    op.alter_column('user', 'phone_number', nullable=True)
