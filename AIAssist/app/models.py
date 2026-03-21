from sqlalchemy import Column, Integer, String, Text, DateTime, func
from pgvector.sqlalchemy import Vector
from app.database import Base

EMBEDDING_DIM = 384  # paraphrase-multilingual-MiniLM-L12-v2


class CourseChunk(Base):
    __tablename__ = "course_chunks"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    course_id          = Column(Integer, nullable=False, index=True)
    cmid               = Column(Integer, nullable=False)
    type               = Column(String(50), default="page")
    section            = Column(Integer, default=0)
    title              = Column(String(500), default="")
    text               = Column(Text, nullable=False)
    position_in_module = Column(Integer, default=0)
    embedding          = Column(Vector(EMBEDDING_DIM))
    created_at         = Column(DateTime, server_default=func.now())


class CourseOverview(Base):
    __tablename__ = "course_overviews"

    course_id    = Column(Integer, primary_key=True)
    overview     = Column(Text, nullable=False, default="")
    generated_at = Column(DateTime, server_default=func.now())


class AssistantLog(Base):
    __tablename__ = "assistant_logs"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    ts             = Column(DateTime, server_default=func.now(), index=True)
    student_id     = Column(Integer, nullable=True)
    course_id      = Column(Integer, nullable=False, index=True)
    question       = Column(Text, nullable=False)
    answer         = Column(Text, nullable=False)
    used_chunk_ids = Column(Text, default="[]")  # JSON array of chunk ids
