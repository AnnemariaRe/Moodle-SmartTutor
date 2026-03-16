from datetime import datetime

from pydantic import BaseModel


# Concept
class ConceptCreate(BaseModel):
    course_id: int
    name: str
    difficulty: float = 0.5


class ConceptOut(BaseModel):
    id: int
    course_id: int
    name: str
    difficulty: float
    is_approved: bool = False

    model_config = {"from_attributes": True}


class ConceptPrereqCreate(BaseModel):
    concept_id: int
    prereq_concept_id: int


class ConceptPrereqOut(BaseModel):
    concept_id: int
    prereq_concept_id: int


# ContentItem
class ContentItemCreate(BaseModel):
    course_id: int
    moodle_cmid: int
    concept_id: int
    type: str  # video | text | quiz
    difficulty: float = 0.5


class ContentItemOut(BaseModel):
    id: int
    course_id: int
    moodle_cmid: int
    concept_id: int
    type: str
    difficulty: float
    role: str = "regular"

    model_config = {"from_attributes": True}


class PlacementTestOut(BaseModel):
    course_id: int
    cmid: int
    content_item_id: int


# AssessmentMap
class AssessmentMapCreate(BaseModel):
    content_item_id: int
    concept_id: int
    weight: float = 1.0


class AssessmentMapOut(BaseModel):
    content_item_id: int
    concept_id: int
    weight: float


# State & Recommendations
class MasteryOut(BaseModel):
    concept_id: int
    concept_name: str
    mastery: float
    updated_at: datetime

    model_config = {"from_attributes": True}


class StudentStateOut(BaseModel):
    student_id: int
    course_id: int
    state: list[MasteryOut]


class RecommendationItem(BaseModel):
    content_item_id: int
    moodle_cmid: int
    type: str
    concept_id: int
    concept_name: str
    difficulty: float
    reason: str


class RecommendationsOut(BaseModel):
    student_id: int
    course_id: int
    method: str = "rule_based"              # "lightfm_hybrid" | "rule_based"
    features_used: list[str] = []           # ["ema_mastery", "attempt_stats", "dkt_prediction"]
    fallback_used: bool = False             # True if LightFM was tried but produced no results

    # Context-aware fields (populated only when cmid is passed)
    current_cmid: int | None = None
    current_concept_id: int | None = None
    current_concept_name: str | None = None
    current_mastery: float | None = None
    current_dkt_p_correct: float | None = None  # P(correct) from DKT, None if model not loaded
    context: str | None = None              # "fix_prerequisites" | "review_current" | "progressing" | "ready_to_continue"
    context_message: str | None = None
    weak_prerequisites: list[str] = []     # concept names with mastery < 0.5

    recommendations: list[RecommendationItem]


# Admin: graph export / import
class AdminGraphOut(BaseModel):
    course_id: int
    concepts: list[ConceptOut]
    prereqs: list[ConceptPrereqOut]
    content_items: list[ContentItemOut]
    assessment_maps: list[AssessmentMapOut]


class ConceptImport(BaseModel):
    """Concept entry in the import payload. name is the natural key within a course."""
    name: str
    difficulty: float = 0.5
    is_approved: bool = True


class PrereqImport(BaseModel):
    concept_name: str
    prereq_concept_name: str


class ContentItemImport(BaseModel):
    moodle_cmid: int
    concept_name: str  # natural key → resolved to concept.id
    type: str
    difficulty: float = 0.5


class AssessmentMapImport(BaseModel):
    moodle_cmid: int       # references ContentItem by cmid within the same course
    concept_name: str      # natural key
    weight: float = 1.0


class GraphImport(BaseModel):
    course_id: int
    concepts: list[ConceptImport]
    prereqs: list[PrereqImport] = []
    content_items: list[ContentItemImport] = []
    assessment_maps: list[AssessmentMapImport] = []
