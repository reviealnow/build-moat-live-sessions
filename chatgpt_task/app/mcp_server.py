import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .db import init_db
from .scheduler import create_job, list_jobs, get_job, cancel_job
from .watcher import watch
from .worker import work

server = Server("task-scheduler")

# ── Tool Registry ────────────────────────────────────────────────────────────
# Maps tool name → callable(arguments dict) → result.
# Adding a new tool = one dict entry, no routing logic to change.

TOOL_REGISTRY: dict[str, callable] = {
    "task_create": lambda a: create_job(a["description"], a["scheduled_at"]),
    "task_list":   lambda a: list_jobs(),
    "task_status": lambda a: get_job(int(a["job_id"])),
    "task_cancel": lambda a: cancel_job(int(a["job_id"])),
}

# ── Tool Schemas ─────────────────────────────────────────────────────────────

_TOOLS = [
    Tool(
        name="task_create",
        description="Schedule a task for future execution.",
        inputSchema={
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What to execute"},
                "scheduled_at": {"type": "string", "description": "ISO 8601 datetime (UTC)"},
            },
            "required": ["description", "scheduled_at"],
        },
    ),
    Tool(
        name="task_list",
        description="List all jobs.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="task_status",
        description="Check a job's status.",
        inputSchema={
            "type": "object",
            "properties": {"job_id": {"type": "integer"}},
            "required": ["job_id"],
        },
    ),
    Tool(
        name="task_cancel",
        description="Cancel a pending or running job.",
        inputSchema={
            "type": "object",
            "properties": {"job_id": {"type": "integer"}},
            "required": ["job_id"],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return _TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = TOOL_REGISTRY.get(name)
    if handler is None:
        result = {"error": f"unknown tool: {name}"}
    else:
        result = handler(arguments)
        if result is None:
            result = {"error": "not found"}
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ── Entry point ──────────────────────────────────────────────────────────────

async def _main():
    init_db()
    queue: asyncio.Queue = asyncio.Queue()
    watcher_task = asyncio.create_task(watch(queue))
    worker_task = asyncio.create_task(work(queue))
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        watcher_task.cancel()
        worker_task.cancel()


if __name__ == "__main__":
    asyncio.run(_main())
