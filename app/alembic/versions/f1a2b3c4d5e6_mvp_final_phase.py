"""mvp_final_phase

Revision ID: f1a2b3c4d5e6
Revises: bf6e316cb322
Create Date: 2026-05-25 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = 'f1a2b3c4d5e6'
down_revision = ('bf6e316cb322', 'c1d2e3f4a5b6')
branch_labels = None
depends_on = None


def upgrade():
    # Alert table
    op.create_table(
        'alert',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('category', sa.Enum('HOTSPOT', 'INCIDENT', 'COMMUNITY_TENSION', 'POLICE_OPERATION', name='alertcategory'), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=False),
        sa.Column('parish_id', sa.Uuid(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('source_report_id', sa.Uuid(), nullable=True),
        sa.Column('source_task_id', sa.Uuid(), nullable=True),
        sa.Column('severity_score', sa.Float(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['parish_id'], ['parish.id']),
        sa.ForeignKeyConstraint(['source_report_id'], ['report.id']),
        sa.ForeignKeyConstraint(['source_task_id'], ['task.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # OTP Record table
    op.create_table(
        'otp_record',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('phone_number', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('otp_hash', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_otp_record_phone_number', 'otp_record', ['phone_number'])

    # Device PIN table
    op.create_table(
        'device_pin',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('device_id', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('pin_hash', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_device_pin_user_id', 'device_pin', ['user_id'])
    op.create_index('ix_device_pin_device_id', 'device_pin', ['device_id'])

    # PDM mock tables (raw SQL — not managed by SQLModel)
    op.execute("create extension if not exists pgcrypto")
    op.execute("""
        create table if not exists pdm_beneficiaries (
            id uuid primary key default gen_random_uuid(),
            external_beneficiary_id text not null unique,
            full_name text not null,
            phone_number text,
            national_id text,
            district text,
            sub_county text,
            parish text,
            program_type text,
            enterprise text,
            raw_payload jsonb not null default '{}'::jsonb,
            last_synced_at timestamptz not null default now(),
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        )
    """)
    op.execute("""
        create table if not exists pdm_disbursements (
            id uuid primary key default gen_random_uuid(),
            external_disbursement_id text not null unique,
            beneficiary_id uuid not null references pdm_beneficiaries(id) on delete cascade,
            beneficiary_external_id text not null,
            amount numeric(18,2) not null,
            currency text not null default 'UGX',
            disbursement_date date,
            status text,
            raw_payload jsonb not null default '{}'::jsonb,
            last_synced_at timestamptz not null default now(),
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        )
    """)
    op.execute("""
        create table if not exists pdm_sync_logs (
            id uuid primary key default gen_random_uuid(),
            source_name text not null default 'mock_pdm',
            sync_type text not null,
            status text not null,
            records_processed integer not null default 0,
            started_at timestamptz not null default now(),
            ended_at timestamptz,
            details jsonb not null default '{}'::jsonb
        )
    """)


def downgrade():
    op.execute("drop table if exists pdm_sync_logs")
    op.execute("drop table if exists pdm_disbursements")
    op.execute("drop table if exists pdm_beneficiaries")
    op.drop_index('ix_device_pin_device_id', table_name='device_pin')
    op.drop_index('ix_device_pin_user_id', table_name='device_pin')
    op.drop_table('device_pin')
    op.drop_index('ix_otp_record_phone_number', table_name='otp_record')
    op.drop_table('otp_record')
    op.drop_table('alert')
    op.execute("drop type if exists alertcategory")
