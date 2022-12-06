"""database"""
import asyncio

from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()
_session = None


class FAQ(Base):
    __tablename__ = "faq"
    chat_id = Column(Integer, primary_key=True)
    question = Column(String, primary_key=True)
    answer = Column(String)


def async_session():
    """Get session"""
    return _session()


async def init(path: str, debug: bool = False) -> None:
    """Initialize engine."""
    global _session
    engine = create_async_engine(path, echo=debug)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    _session = sessionmaker(engine, class_=AsyncSession)
