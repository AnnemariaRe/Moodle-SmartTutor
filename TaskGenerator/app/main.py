import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.admin_router import router as admin_router
from app.database import init_db
from app.router import router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Personalized Tasks Service", version="1.0.0", lifespan=lifespan)
app.include_router(router)
app.include_router(admin_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}
