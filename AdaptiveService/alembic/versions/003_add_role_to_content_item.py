"""add role to content_item

Revision ID: 003
Revises: 002
Create Date: 2025-01-03 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_item",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default="regular",
        ),
    )


def downgrade() -> None:
    op.drop_column("content_item", "role")
