from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class GeneratedTask(Base):
    __tablename__ = "generated_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, nullable=False, index=True)
    course_id = Column(Integer, nullable=False, index=True)
    concept_id = Column(Integer, nullable=False)
    concept_name = Column(String(255), nullable=False)
    json_spec = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="draft")  # draft | approved | used
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class TaskAttempt(Base):
    __tablename__ = "task_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("generated_tasks.id", ondelete="SET NULL"), nullable=True)
    student_id = Column(Integer, nullable=False, index=True)
    concept_id = Column(Integer, nullable=False, index=True)
    difficulty = Column(String(20), nullable=False)   # easy | medium | hard
    score = Column(Float, nullable=False)              # 0.0 – 1.0
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
