"""geo_hierarchy_expansion

Revision ID: a9b8c7d6e5f4
Revises: f1a2b3c4d5e6
Create Date: 2026-05-28 14:00:00.000000

Expands the 4-level geo hierarchy (region→sector→district→parish)
to the full 7-level Uganda administrative structure:
  region → sector → district → county → subcounty → parish → village

Changes:
- Rename sector unique constraint to match new naming
- Add unique constraint on district(name, sector_id) replacing old one
- Drop old parish table (had district_id FK, incompatible with new structure)
- Create county, subcounty, new parish (subcounty_id FK), village tables
- Change user.geographical_id FK from parish.id → subcounty.id
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = 'a9b8c7d6e5f4'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    # ── district unique constraint already correct (uq_district_name_sector) ──
    # Nothing to do for district constraints.

    # ── Drop old parish (had district_id FK — incompatible) ──────────────────
    # First drop FKs that reference parish.id
    op.drop_constraint('alert_parish_id_fkey', 'alert', type_='foreignkey')
    op.drop_constraint('beneficiary_parish_id_fkey', 'beneficiary', type_='foreignkey')
    op.drop_constraint('report_parish_id_fkey', 'report', type_='foreignkey')
    op.drop_constraint('user_geographical_id_fkey', 'user', type_='foreignkey')
    op.drop_table('parish')

    # ── Create county ─────────────────────────────────────────────────────────
    op.create_table(
        'county',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('district_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['district_id'], ['district.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'district_id', name='uq_county_name_district'),
    )

    # ── Create subcounty ──────────────────────────────────────────────────────
    op.create_table(
        'subcounty',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('county_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['county_id'], ['county.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'county_id', name='uq_subcounty_name_county'),
    )

    # ── Create parish (now references subcounty) ──────────────────────────────
    op.create_table(
        'parish',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('subcounty_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['subcounty_id'], ['subcounty.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'subcounty_id', name='uq_parish_name_subcounty'),
    )

    # ── Create village ────────────────────────────────────────────────────────
    op.create_table(
        'village',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('parish_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['parish_id'], ['parish.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'parish_id', name='uq_village_name_parish'),
    )

    # ── Change user.geographical_id FK → subcounty.id ─────────────────────────
    # Null out stale values (old parish IDs no longer valid)
    op.execute('UPDATE "user" SET geographical_id = NULL')
    op.add_foreign_key_constraint = None  # handled below
    op.create_foreign_key(
        'user_geographical_id_fkey', 'user',
        'subcounty', ['geographical_id'], ['id'],
    )

    # ── Re-add FKs on alert, beneficiary, report pointing to new parish ───────
    # Null out stale parish_id values (old parish IDs no longer exist — reseeding)
    op.execute('UPDATE alert SET parish_id = NULL')
    op.execute('UPDATE report SET parish_id = NULL')
    # beneficiary.parish_id: GISO-level PDM field — null stale values, reseeded later
    op.execute('UPDATE beneficiary SET parish_id = NULL')
    op.create_foreign_key('alert_parish_id_fkey', 'alert', 'parish', ['parish_id'], ['id'])
    op.create_foreign_key('report_parish_id_fkey', 'report', 'parish', ['parish_id'], ['id'])
    op.create_foreign_key('beneficiary_parish_id_fkey', 'beneficiary', 'parish', ['parish_id'], ['id'])


def downgrade():
    op.drop_constraint('report_parish_id_fkey', 'report', type_='foreignkey')
    op.drop_constraint('beneficiary_parish_id_fkey', 'beneficiary', type_='foreignkey')
    op.drop_constraint('alert_parish_id_fkey', 'alert', type_='foreignkey')
    op.drop_constraint('user_geographical_id_fkey', 'user', type_='foreignkey')
    op.drop_table('village')
    op.drop_table('parish')
    op.drop_table('subcounty')
    op.drop_table('county')
    op.create_table(
        'parish',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('district_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['district_id'], ['district.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'district_id', name='uq_parish_name_district'),
    )
    op.create_foreign_key('user_geographical_id_fkey', 'user', 'parish', ['geographical_id'], ['id'])
    op.create_foreign_key('alert_parish_id_fkey', 'alert', 'parish', ['parish_id'], ['id'])
    op.create_foreign_key('beneficiary_parish_id_fkey', 'beneficiary', 'parish', ['parish_id'], ['id'])
    op.create_foreign_key('report_parish_id_fkey', 'report', 'parish', ['parish_id'], ['id'])
    op.drop_constraint('uq_district_name_sector', 'district', type_='unique')
    op.create_unique_constraint('uq_district_name_sector', 'district', ['name', 'sector_id'])
