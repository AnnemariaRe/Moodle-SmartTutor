"""add is_approved to concept

Revision ID: 002
Revises: 001
Create Date: 2025-01-01 00:00:01.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "concept",
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("concept", "is_approved")
