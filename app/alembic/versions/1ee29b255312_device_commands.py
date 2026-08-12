"""device_commands

Revision ID: 1ee29b255312
Revises: e5f6a7b8c9d0
Create Date: 2026-05-18 12:42:01.947344

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '1ee29b255312'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('device_command',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('issued_by', sa.Uuid(), nullable=False),
    sa.Column('command', sa.Enum('LOGOUT', 'DISABLE', 'ENABLE', 'WIPE', name='devicecommandtype'), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'DELIVERED', 'ACKNOWLEDGED', name='devicecommandstatus'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['issued_by'], ['user.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_device_command_user_id'), 'device_command', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_device_command_user_id'), table_name='device_command')
    op.drop_table('device_command')
