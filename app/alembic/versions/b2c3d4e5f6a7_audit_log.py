"""audit_log table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-07 23:55:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('actor_id', sa.Uuid(), nullable=False),
        sa.Column('action', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column('entity_type', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column('entity_id', sa.Uuid(), nullable=False),
        sa.Column('detail', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_log_actor_id', 'audit_log', ['actor_id'])
    op.create_index('ix_audit_log_entity_type', 'audit_log', ['entity_type'])


def downgrade():
    op.drop_index('ix_audit_log_entity_type', table_name='audit_log')
    op.drop_index('ix_audit_log_actor_id', table_name='audit_log')
    op.drop_table('audit_log')
