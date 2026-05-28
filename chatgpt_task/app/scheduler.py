from datetime import datetime, timezone
from .db import Job, get_session


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc(s: str) -> datetime:
    """Parse ISO string; treat naive datetimes as UTC."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _time_bucket(dt: datetime) -> str:
    """Partition key: 'YYYY-MM-DD-HH' — only the current-hour slice is scanned."""
    return dt.strftime("%Y-%m-%d-%H")


def _to_dict(job: Job) -> dict:
    return {
        "job_id": job.id,
        "description": job.description,
        "scheduled_at": job.scheduled_at,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


# ── CRUD ────────────────────────────────────────────────────────────────────

def create_job(description: str, scheduled_at: str) -> dict:
    dt = _to_utc(scheduled_at)
    now_iso = _now().isoformat()
    with get_session() as session:
        job = Job(
            description=description,
            scheduled_at=dt.isoformat(),
            time_bucket=_time_bucket(dt),
            status="pending",
            created_at=now_iso,
            updated_at=now_iso,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return _to_dict(job)


def list_jobs() -> list[dict]:
    with get_session() as session:
        return [_to_dict(j) for j in session.query(Job).order_by(Job.id).all()]


def get_job(job_id: int) -> dict | None:
    with get_session() as session:
        job = session.get(Job, job_id)
        return _to_dict(job) if job else None


def cancel_job(job_id: int) -> dict | None:
    with get_session() as session:
        job = session.get(Job, job_id)
        if job is None:
            return None
        if job.status in ("pending", "running"):
            job.status = "cancelled"
            job.updated_at = _now().isoformat()
            session.commit()
            session.refresh(job)
        return _to_dict(job)


# ── Watcher helpers ──────────────────────────────────────────────────────────

def find_due_jobs() -> list[dict]:
    """
    Time-bucket scan: only rows whose bucket <= current bucket are read.
    Without this, a full table scan hits every row at 1M+ jobs.
    """
    now = _now()
    current_bucket = _time_bucket(now)
    now_iso = now.isoformat()
    with get_session() as session:
        jobs = (
            session.query(Job)
            .filter(
                Job.status == "pending",
                Job.time_bucket <= current_bucket,
                Job.scheduled_at <= now_iso,
            )
            .all()
        )
        return [_to_dict(j) for j in jobs]


def mark_running(job_id: int):
    with get_session() as session:
        job = session.get(Job, job_id)
        if job and job.status == "pending":
            job.status = "running"
            job.updated_at = _now().isoformat()
            session.commit()


def mark_completed(job_id: int):
    with get_session() as session:
        job = session.get(Job, job_id)
        if job and job.status == "running":
            job.status = "completed"
            job.updated_at = _now().isoformat()
            session.commit()
