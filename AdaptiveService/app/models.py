from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Concept(Base):
    __tablename__ = "concept"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    difficulty: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    prerequisites: Mapped[list["ConceptPrereq"]] = relationship(
        "ConceptPrereq",
        foreign_keys="ConceptPrereq.concept_id",
        back_populates="concept",
    )
    content_items: Mapped[list["ContentItem"]] = relationship(
        "ContentItem", back_populates="concept"
    )
    masteries: Mapped[list["StudentConceptMastery"]] = relationship(
        "StudentConceptMastery", back_populates="concept"
    )


class ConceptPrereq(Base):
    """Directed edge: concept_id requires prereq_concept_id first."""

    __tablename__ = "concept_prereq"

    concept_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("concept.id", ondelete="CASCADE"), primary_key=True
    )
    prereq_concept_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("concept.id", ondelete="CASCADE"), primary_key=True
    )

    concept: Mapped["Concept"] = relationship(
        "Concept", foreign_keys=[concept_id], back_populates="prerequisites"
    )
    prereq: Mapped["Concept"] = relationship(
        "Concept", foreign_keys=[prereq_concept_id]
    )


class ContentItem(Base):
    """A Moodle course module mapped to a concept (video / text / quiz)."""

    __tablename__ = "content_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    moodle_cmid: Mapped[int] = mapped_column(Integer, nullable=False)
    concept_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("concept.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # video | text | quiz
    difficulty: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="regular")  # regular | placement

    concept: Mapped["Concept"] = relationship("Concept", back_populates="content_items")
    assessment_maps: Mapped[list["AssessmentMap"]] = relationship(
        "AssessmentMap", back_populates="content_item"
    )


class AssessmentMap(Base):
    """One quiz can assess multiple concepts with different weights."""

    __tablename__ = "assessment_map"

    content_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_item.id", ondelete="CASCADE"), primary_key=True
    )
    concept_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("concept.id", ondelete="CASCADE"), primary_key=True
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    content_item: Mapped["ContentItem"] = relationship(
        "ContentItem", back_populates="assessment_maps"
    )
    concept: Mapped["Concept"] = relationship("Concept")


class StudentConceptMastery(Base):
    """Current mastery level of a student for a concept in a course (0.0–1.0)."""

    __tablename__ = "student_concept_mastery"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", "concept_id", name="uq_scm"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    concept_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("concept.id", ondelete="CASCADE"), nullable=False
    )
    mastery: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    concept: Mapped["Concept"] = relationship("Concept", back_populates="masteries")


class StudentConceptStats(Base):
    """Attempt history per student/concept: counts and recency for recommendation scoring."""

    __tablename__ = "student_concept_stats"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", "concept_id", name="uq_scs"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    concept_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("concept.id", ondelete="CASCADE"), nullable=False
    )
    num_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    num_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
