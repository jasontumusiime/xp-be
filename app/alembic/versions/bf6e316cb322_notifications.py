"""notifications

Revision ID: bf6e316cb322
Revises: 1ee29b255312
Create Date: 2026-05-18 15:52:00.907493

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'bf6e316cb322'
down_revision = '1ee29b255312'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('notification',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('type', sa.Enum('TASK', 'REPORT', 'ALERT', 'INFO', name='notificationtype'), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('message', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=False),
    sa.Column('read', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notification_user_id'), 'notification', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_notification_user_id'), table_name='notification')
    op.drop_table('notification')
