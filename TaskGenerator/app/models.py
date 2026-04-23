from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class GeneratedTask(Base):
    __tablename__ = "generated_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, nullable=True, index=True)  # null for bank tasks
    course_id = Column(Integer, nullable=False, index=True)
    concept_id = Column(Integer, nullable=False)
    concept_name = Column(String(255), nullable=False)
    difficulty = Column(String(20), nullable=True, index=True)  # easy | medium | hard
    json_spec = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="pending_review")  # pending_review | approved | rejected
    teacher_id = Column(Integer, nullable=True)
    teacher_instructions = Column(Text, nullable=True)
    batch_id = Column(String(36), nullable=True, index=True)
    reviewed_by = Column(Integer, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class TaskAttempt(Base):
    __tablename__ = "task_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("generated_tasks.id", ondelete="SET NULL"), nullable=True)
    student_id = Column(Integer, nullable=False, index=True)
    concept_id = Column(Integer, nullable=False, index=True)
    difficulty = Column(String(20), nullable=False)   # easy | medium | hard
    score = Column(Float, nullable=False)              # 0.0 – 1.0
    attempt_no = Column(Integer, nullable=False, default=1)  # attempt number within current cycle
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
