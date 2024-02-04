"""database"""

from contextlib import contextmanager
from threading import Lock

from sqlalchemy import Column, Integer, LargeBinary, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()
_Session = sessionmaker()
_lock = Lock()
_session = None  # noqa


class FAQ(Base):  # noqa
    __tablename__ = "faq"
    chat_id = Column(Integer, primary_key=True)
    question = Column(String, primary_key=True)
    answer_text = Column(String)
    answer_html = Column(String)
    answer_file = Column(LargeBinary)
    answer_filename = Column(String)
    answer_viewtype = Column(String, nullable=False)


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    with _lock:
        session = _Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def init(path: str, debug: bool = False) -> None:
    """Initialize engine."""
    engine = create_engine(path, echo=debug)
    Base.metadata.create_all(engine)
    _Session.configure(bind=engine)
