"""SQLAlchemy 基础配置 — Engine + Session + Base."""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """声明式基类."""

    pass


# 从环境变量读取数据库 URL，仅支持 PostgreSQL
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://wirewolf:wirewolf@localhost:5433/wirewolf")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
)

# 异步 Session 工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
