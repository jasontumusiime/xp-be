"""pdm_consolidation

Revision ID: f3c56fc58253
Revises: b1c2d3e4f5a6
Create Date: 2026-06-01 09:21:55.606460

Adds PDM verification fields to report, task, and disbursement tables.
NOTE: pdm_beneficiaries, pdm_disbursements, pdm_sync_logs are external sync
tables and are intentionally left untouched.
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

revision = 'f3c56fc58253'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    # report: add program_type, pdm_beneficiary_id, pdm_disbursement_id, outcome
    # (linking directly to the sync tables, not the local beneficiary/disbursement tables)
    op.add_column('report', sa.Column('program_type', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True))
    op.add_column('report', sa.Column('pdm_beneficiary_id', sa.Uuid(), nullable=True))
    op.add_column('report', sa.Column('pdm_disbursement_id', sa.Uuid(), nullable=True))
    op.add_column('report', sa.Column('outcome', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True))
    op.create_index('ix_report_program_type', 'report', ['program_type'], unique=False)
    op.create_foreign_key('fk_report_pdm_beneficiary_id', 'report', 'pdm_beneficiaries', ['pdm_beneficiary_id'], ['id'])
    op.create_foreign_key('fk_report_pdm_disbursement_id', 'report', 'pdm_disbursements', ['pdm_disbursement_id'], ['id'])

    # task: add program_type, pdm_beneficiary_id, pdm_disbursement_id
    op.add_column('task', sa.Column('program_type', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True))
    op.add_column('task', sa.Column('pdm_beneficiary_id', sa.Uuid(), nullable=True))
    op.add_column('task', sa.Column('pdm_disbursement_id', sa.Uuid(), nullable=True))
    op.create_index('ix_task_program_type', 'task', ['program_type'], unique=False)
    op.create_foreign_key('fk_task_pdm_beneficiary_id', 'task', 'pdm_beneficiaries', ['pdm_beneficiary_id'], ['id'])
    op.create_foreign_key('fk_task_pdm_disbursement_id', 'task', 'pdm_disbursements', ['pdm_disbursement_id'], ['id'])

    # pdm_disbursements: add verification_status derived from linked reports
    op.add_column('pdm_disbursements', sa.Column('verification_status', sa.String(), nullable=False, server_default='UNVERIFIED'))


def downgrade():
    op.drop_column('pdm_disbursements', 'verification_status')

    op.drop_constraint('fk_task_pdm_disbursement_id', 'task', type_='foreignkey')
    op.drop_constraint('fk_task_pdm_beneficiary_id', 'task', type_='foreignkey')
    op.drop_index('ix_task_program_type', table_name='task')
    op.drop_column('task', 'pdm_disbursement_id')
    op.drop_column('task', 'pdm_beneficiary_id')
    op.drop_column('task', 'program_type')

    op.drop_constraint('fk_report_pdm_disbursement_id', 'report', type_='foreignkey')
    op.drop_constraint('fk_report_pdm_beneficiary_id', 'report', type_='foreignkey')
    op.drop_index('ix_report_program_type', table_name='report')
    op.drop_column('report', 'outcome')
    op.drop_column('report', 'pdm_disbursement_id')
    op.drop_column('report', 'pdm_beneficiary_id')
    op.drop_column('report', 'program_type')
