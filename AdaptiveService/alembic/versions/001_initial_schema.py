"""initial adaptive schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concept",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("difficulty", sa.Float(), nullable=False, server_default="0.5"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_concept_course_id", "concept", ["course_id"])

    op.create_table(
        "concept_prereq",
        sa.Column("concept_id", sa.Integer(), nullable=False),
        sa.Column("prereq_concept_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["concept_id"], ["concept.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["prereq_concept_id"], ["concept.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("concept_id", "prereq_concept_id"),
    )

    op.create_table(
        "content_item",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("moodle_cmid", sa.Integer(), nullable=False),
        sa.Column("concept_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("difficulty", sa.Float(), nullable=False, server_default="0.5"),
        sa.ForeignKeyConstraint(["concept_id"], ["concept.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_content_item_course_id", "content_item", ["course_id"])

    op.create_table(
        "assessment_map",
        sa.Column("content_item_id", sa.Integer(), nullable=False),
        sa.Column("concept_id", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.ForeignKeyConstraint(
            ["content_item_id"], ["content_item.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["concept_id"], ["concept.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("content_item_id", "concept_id"),
    )

    op.create_table(
        "student_concept_mastery",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("concept_id", sa.Integer(), nullable=False),
        sa.Column("mastery", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["concept_id"], ["concept.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "student_id", "course_id", "concept_id", name="uq_scm"
        ),
    )
    op.create_index(
        "ix_student_concept_mastery_student_id",
        "student_concept_mastery",
        ["student_id"],
    )
    op.create_index(
        "ix_student_concept_mastery_course_id",
        "student_concept_mastery",
        ["course_id"],
    )


def downgrade() -> None:
    op.drop_table("student_concept_mastery")
    op.drop_table("assessment_map")
    op.drop_table("content_item")
    op.drop_table("concept_prereq")
    op.drop_table("concept")
