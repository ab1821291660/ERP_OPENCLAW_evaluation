from typing import Generator

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.config import PROJECT_ROOT, get_settings
class Base(DeclarativeBase):
    """所有 agent.db ORM 模型共享的 SQLAlchemy Declarative 基类。"""
    pass
settings = get_settings()



# SQLite 相对文件路径固定以项目根目录为基准，而不是 PyCharm 的工作目录。
database_url = make_url(settings.database_url)
if database_url.get_backend_name() == "sqlite" and database_url.database not in {None, "", ":memory:"}:
    database_path = Path(database_url.database)
    if not database_path.is_absolute():
        database_url = database_url.set(database=str((PROJECT_ROOT / database_path).resolve()))

engine = create_engine(
    database_url,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

def get_db() -> Generator[Session, None, None]:
    """为每个请求生成新的数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
