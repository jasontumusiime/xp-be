"""pdm tables: beneficiary and disbursement

Revision ID: a1b2c3d4e5f6
Revises: ef29987e3977
Create Date: 2026-05-07 23:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

revision = 'a1b2c3d4e5f6'
down_revision = 'ef29987e3977'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'beneficiary',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('full_name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('national_id', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column('phone_number', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
        sa.Column('parish_id', sa.Uuid(), nullable=True),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('verified_by', sa.Uuid(), nullable=True),
        sa.Column('notes', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['parish_id'], ['parish.id']),
        sa.ForeignKeyConstraint(['verified_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('national_id'),
    )
    op.create_index('ix_beneficiary_national_id', 'beneficiary', ['national_id'])

    op.create_table(
        'disbursement',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('beneficiary_id', sa.Uuid(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('disbursed_by', sa.Uuid(), nullable=True),
        sa.Column('disbursed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['beneficiary_id'], ['beneficiary.id']),
        sa.ForeignKeyConstraint(['disbursed_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('disbursement')
    op.drop_index('ix_beneficiary_national_id', table_name='beneficiary')
    op.drop_table('beneficiary')
