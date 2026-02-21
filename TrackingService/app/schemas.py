from pydantic import BaseModel


class Event(BaseModel):
    event_id: str
    ts: int
    student_id: int
    course_id: int
    event_type: str
    object_type: str
    object_id: int
    cmid: int | None = None
    payload: dict = {}


class EventResponse(BaseModel):
    status: str
    event_id: str
