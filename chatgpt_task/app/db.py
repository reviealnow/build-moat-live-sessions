from sqlalchemy import create_engine, Column, Integer, String, Index
from sqlalchemy.orm import DeclarativeBase, Session
import os

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "jobs.db")
engine = create_engine(
    f"sqlite:///{_DB_PATH}",
    connect_args={"check_same_thread": False},
)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    description = Column(String, nullable=False)
    scheduled_at = Column(String, nullable=False)   # UTC ISO-8601
    time_bucket = Column(String, nullable=False)    # "YYYY-MM-DD-HH"
    status = Column(String, nullable=False, default="pending")
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


# Index on (time_bucket, status) — the watcher's hot path
_bucket_idx = Index("ix_jobs_bucket_status", Job.time_bucket, Job.status)


def init_db():
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
