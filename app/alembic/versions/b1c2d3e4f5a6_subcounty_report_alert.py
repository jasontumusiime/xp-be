"""add_subcounty_id_to_report_and_alert

Revision ID: b1c2d3e4f5a6
Revises: a9b8c7d6e5f4
Create Date: 2026-05-31 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "a9b8c7d6e5f4"
branch_labels = None
depends_on = None


def upgrade():
    # report: add subcounty_id
    op.add_column("report", sa.Column("subcounty_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_report_subcounty", "report", "subcounty", ["subcounty_id"], ["id"])
    op.create_index("ix_report_subcounty_id", "report", ["subcounty_id"])

    # alert: add subcounty_id + indexes on is_active, category, created_at
    op.add_column("alert", sa.Column("subcounty_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_alert_subcounty", "alert", "subcounty", ["subcounty_id"], ["id"])
    op.create_index("ix_alert_subcounty_id", "alert", ["subcounty_id"])
    op.create_index("ix_alert_is_active", "alert", ["is_active"])
    op.create_index("ix_alert_category", "alert", ["category"])
    op.create_index("ix_alert_created_at", "alert", ["created_at"])


def downgrade():
    op.drop_index("ix_alert_created_at", "alert")
    op.drop_index("ix_alert_category", "alert")
    op.drop_index("ix_alert_is_active", "alert")
    op.drop_constraint("fk_alert_subcounty", "alert", type_="foreignkey")
    op.drop_index("ix_alert_subcounty_id", "alert")
    op.drop_column("alert", "subcounty_id")

    op.drop_constraint("fk_report_subcounty", "report", type_="foreignkey")
    op.drop_index("ix_report_subcounty_id", "report")
    op.drop_column("report", "subcounty_id")
