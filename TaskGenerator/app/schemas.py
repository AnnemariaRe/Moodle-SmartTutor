from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

MASTERY_PASSED = 0.7  # score threshold to consider a task attempt successful


class TaskSpec(BaseModel):
    type: str = Field(..., description="mcq | open | code")
    difficulty: str = Field(..., description="easy|medium|hard")
    question: str
    options: Optional[List[str]] = None
    correct_index: Optional[int] = None
    correct_answer: Optional[str] = None
    explanation: str


class PersonalizedTaskRequest(BaseModel):
    student_id: int
    course_id: int
    max_concepts: int = 2
    variants_per_concept: int = 2
    mastery_threshold: float = 0.7


class TaskResponse(BaseModel):
    id: int
    concept_id: int
    concept_name: str
    spec: TaskSpec


class PersonalizedTaskResponse(BaseModel):
    tasks: List[TaskResponse]


class ConceptMastery(BaseModel):
    concept_id: int
    concept_name: str
    mastery: float
    updated_at: datetime

    model_config = {"from_attributes": True}


class CheckAnswerRequest(BaseModel):
    task_id: int
    student_id: int
    answer: dict


class CheckAnswerResponse(BaseModel):
    score: float
    correct: bool
    explanation: str


# ── Teacher / Admin schemas ────────────────────────────────────────────────

class BatchGenerateRequest(BaseModel):
    course_id: int
    teacher_id: int
    teacher_instructions: Optional[str] = None
    tasks_per_concept: int = Field(default=9, ge=1, le=30)
    difficulties: List[str] = Field(default=["easy", "medium", "hard"])


class BatchGenerateResponse(BaseModel):
    batch_id: str
    total_tasks: int
    concepts_covered: int


class TaskBankItem(BaseModel):
    id: int
    concept_id: int
    concept_name: str
    difficulty: str
    spec: TaskSpec
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskBankListResponse(BaseModel):
    tasks: List[TaskBankItem]
    total: int


class TaskReviewRequest(BaseModel):
    task_id: int
    action: str = Field(..., description="approve | reject")
    reviewed_by: int
    edited_spec: Optional[TaskSpec] = None


class TaskReviewResponse(BaseModel):
    id: int
    status: str


class BulkReviewRequest(BaseModel):
    task_ids: List[int]
    action: str = Field(..., description="approve | reject")
    reviewed_by: int
