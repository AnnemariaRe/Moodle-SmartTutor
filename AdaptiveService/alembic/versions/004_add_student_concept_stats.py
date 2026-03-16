"""add student_concept_stats

Revision ID: 004
Revises: 003
Create Date: 2025-01-04 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_concept_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("concept_id", sa.Integer(), nullable=False),
        sa.Column("num_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("num_correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["concept_id"], ["concept.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "course_id", "concept_id", name="uq_scs"),
    )
    op.create_index("ix_scs_student_id", "student_concept_stats", ["student_id"])
    op.create_index("ix_scs_course_id", "student_concept_stats", ["course_id"])


def downgrade() -> None:
    op.drop_table("student_concept_stats")
