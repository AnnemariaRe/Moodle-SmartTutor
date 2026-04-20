from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.settings import settings
from app.models import Base

engine = create_async_engine(settings.database_url, echo=False, connect_args={"ssl": False})
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
