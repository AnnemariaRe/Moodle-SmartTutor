from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


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
    answer: dict


class CheckAnswerResponse(BaseModel):
    score: float
    correct: bool
    explanation: str
