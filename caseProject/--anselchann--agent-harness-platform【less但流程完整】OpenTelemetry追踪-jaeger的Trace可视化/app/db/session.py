from functools import lru_cache

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
@lru_cache
def _engine():
    kwargs = {}
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_async_engine(settings.database_url, echo=settings.debug, **kwargs)
def _sessionmaker():
    return async_sessionmaker(_engine(), expire_on_commit=False)
async def get_db():
    maker = _sessionmaker()
    async with maker() as session:
        try:
            yield session
        finally:
            await session.close()
