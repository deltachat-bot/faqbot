"""database"""
import asyncio

from sqlalchemy import Column, Integer, LargeBinary, String
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()
_session = None


class FAQ(Base):
    __tablename__ = "faq"
    chat_id = Column(Integer, primary_key=True)
    question = Column(String, primary_key=True)
    answer_text = Column(String)
    answer_html = Column(String)
    answer_file = Column(LargeBinary)
    answer_filename = Column(String)
    answer_viewtype = Column(String, nullable=False)


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
