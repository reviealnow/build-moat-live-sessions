import asyncio
from .scheduler import mark_completed


async def work(queue: asyncio.Queue):
    """Pull job IDs from the queue and mark them completed."""
    while True:
        job_id = await queue.get()
        # Simulate execution — replace with real dispatch logic here
        await asyncio.sleep(0.1)
        mark_completed(job_id)
        queue.task_done()
