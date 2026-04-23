from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=4000)


class AskRequest(BaseModel):
    student_id: Optional[int] = None
    course_id: int
    question: str = Field(..., min_length=1, max_length=2000)
    history: List[HistoryMessage] = Field(default_factory=list, max_length=20)


class SourceItem(BaseModel):
    cmid: int
    title: str
    type: str


class AskResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    course_id: int


class ReindexResponse(BaseModel):
    course_id: int
    chunks_created: int
    message: str


class SearchRequest(BaseModel):
    course_id: int
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchChunk(BaseModel):
    text: str
    source_module_id: int
    source_module_name: str
    type: str
    score: float


class SearchResponse(BaseModel):
    chunks: List[SearchChunk]
