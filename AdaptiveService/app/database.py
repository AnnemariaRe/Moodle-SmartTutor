import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://adaptive:adaptive@postgres:5432/adaptive",
)

engine = create_async_engine(DATABASE_URL, echo=False, connect_args={"ssl": False})
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@asynccontextmanager
async def get_adaptive_db_session():
    async with AsyncSessionLocal() as session:
        yield session
