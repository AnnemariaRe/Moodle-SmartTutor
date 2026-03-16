import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.admin_router import router as admin_router
from app.events_consumer import consume_events
from app.router import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer_task = asyncio.create_task(consume_events())
    logger.info("RabbitMQ consumer started")

    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
        logger.info("RabbitMQ consumer stopped")


app = FastAPI(title="Adaptive Service", version="1.0.0", lifespan=lifespan)

app.include_router(router)
app.include_router(admin_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}
