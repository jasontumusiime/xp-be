"""remove program_type from task

Revision ID: a1b2c3d4e5f6
Revises: f3c56fc58253
Create Date: 2026-06-02
"""
from alembic import op

revision = 'ee1a2b3c4d5f'
down_revision = 'f3c56fc58253'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index('ix_task_program_type', table_name='task', if_exists=True)
    op.drop_column('task', 'program_type')


def downgrade():
    import sqlmodel
    import sqlalchemy as sa
    op.add_column('task', sa.Column('program_type', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True))
    op.create_index('ix_task_program_type', 'task', ['program_type'], unique=False)
