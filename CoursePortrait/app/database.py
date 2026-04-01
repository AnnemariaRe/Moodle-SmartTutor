"""
Database (PostgreSQL) and Redis connection setup.

PostgreSQL is used for storing aggregated course metrics.
Redis is used for caching API responses.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, Float, String, DateTime, Text, Index
from datetime import datetime
import os
from typing import Optional
import redis.asyncio as redis

# ========== CONNECTION SETTINGS ==========

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:pass@postgres:5434/portrait"
)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# ========== SQLALCHEMY SETTINGS ==========
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)
Base = declarative_base()


# ========== DB MODELS ==========

class CourseMetrics(Base):
    __tablename__ = "course_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    courseId = Column(Integer, index=True, nullable=False)
    moduleId = Column(Integer, index=True, nullable=False)
    sectionId = Column(Integer, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    avg_duration_ms = Column(Float, comment="Average session duration in module (ms)")
    watch_percent = Column(Float, comment="Video watch percentage (0-1)")
    dropout_rate = Column(Float, comment="Dropout rate after module (0-1)")
    student_count = Column(Integer, comment="Number of students who opened the module")
    pause_count_avg = Column(Float, comment="Average number of video pauses")

    difficulty_score = Column(Float, comment="Composite difficulty index (0-1)")
    dropout_risk = Column(Float, comment="ML predicted dropout risk (0-1)")
    
    __table_args__ = (
        Index('idx_course_module', 'courseId', 'moduleId'),
        Index('idx_course_timestamp', 'courseId', 'timestamp'),
    )


class SequencePath(Base):
    __tablename__ = "sequences"
    
    id = Column(Integer, primary_key=True, index=True)
    courseId = Column(Integer, index=True, nullable=False)
    studentId = Column(String, index=True, comment="Anonymous student ID")
    step_path = Column(Text, comment="JSON array of moduleId in completion order")
    ended_with_dropout = Column(Integer, default=0, comment="1 if ended with dropout")
    total_time_ms = Column(Float, comment="Total completion time (ms)")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index('idx_course_student', 'courseId', 'studentId'),
    )


# ========== REDIS CLIENT ==========

redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None


# ========== DB DEPENDENCY ==========

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
