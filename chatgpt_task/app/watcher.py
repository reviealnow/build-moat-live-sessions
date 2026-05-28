import asyncio
from .scheduler import find_due_jobs, mark_running


async def watch(queue: asyncio.Queue, interval: float = 1.0):
    """Scan for due jobs every `interval` seconds and enqueue their IDs."""
    while True:
        for job in find_due_jobs():
            mark_running(job["job_id"])
            await queue.put(job["job_id"])
        await asyncio.sleep(interval)
