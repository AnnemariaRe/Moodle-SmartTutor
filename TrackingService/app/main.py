import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import rabbitmq
from app.database import get_db, init_db
from app.models import EventRecord
from app.schemas import Event, EventResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Database initialized")
    try:
        await rabbitmq.connect()
    except Exception:
        logger.warning("Could not connect to RabbitMQ on startup — will retry per-publish")
    yield
    await rabbitmq.disconnect()


app = FastAPI(title="Tracking Service", version="1.0.0", lifespan=lifespan)


@app.post("/v1/events", status_code=status.HTTP_202_ACCEPTED, response_model=EventResponse)
async def track_event(event: Event, db: AsyncSession = Depends(get_db)):
    logger.info(
        "[RECEIVE] event_id=%s event_type=%s student_id=%s course_id=%s cmid=%s",
        event.event_id, event.event_type, event.student_id, event.course_id, event.cmid,
    )

    record = EventRecord(
        event_id=event.event_id,
        ts=event.ts,
        student_id=event.student_id,
        course_id=event.course_id,
        event_type=event.event_type,
        object_type=event.object_type,
        object_id=event.object_id,
        cmid=event.cmid,
        payload=event.payload,
    )
    try:
        db.add(record)
        await db.commit()
        logger.info("[SAVED] event_id=%s → Postgres", event.event_id)
    except IntegrityError:
        await db.rollback()
        logger.warning("[SKIP] event_id=%s already exists", event.event_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Event with event_id={event.event_id!r} already exists",
        )

    await rabbitmq.publish_event(event.model_dump())
    logger.info("[PUBLISH] event_id=%s routing_key=%s → RabbitMQ", event.event_id, event.event_type)

    return EventResponse(status="ok", event_id=event.event_id)


@app.get("/health")
async def health():
    return {"status": "healthy"}
