# ChatGPT Task Scheduler — MCP Server

A real **MCP (Model Context Protocol)** stdio server that lets Claude — or any MCP client — schedule and manage tasks via standardized tool calls. Built as the Challenge Track implementation for the Build Moat Week 3 exercise.

## Key Design Decisions

1. **Watcher + Queue + Worker** — Decoupled architecture: watcher scans DB for due jobs → pushes to asyncio queue → worker executes independently (in-memory queue simulates SQS)
2. **Time Bucket Partitioning** — Jobs are partitioned by hour (`YYYY-MM-DD-HH`), so the watcher only scans the current-hour slice (avoids full table scans at 1M+ jobs)
3. **MCP Tool Registry Pattern** — `TOOL_REGISTRY` dict routes tool calls to handlers (avoids if-else anti-pattern when adding new tools)
4. **Underscore Naming** — `task_create`, `task_status` instead of `task.create` (dots are valid in MCP protocol but rejected by Claude Desktop frontend)

## MCP Tools

| Tool | Description |
|---|---|
| `task_create` | Schedule a new task for future execution |
| `task_list` | List all scheduled tasks |
| `task_status` | Get the status of a scheduled task |
| `task_cancel` | Cancel a pending or running task |

## Project Structure

```
chatgpt_task/
├── app/                         # Challenge track implementation
│   ├── mcp_server.py            # MCP entry point + tool registry
│   ├── scheduler.py             # CRUD + time bucket scan logic
│   ├── watcher.py               # Async watcher (scans DB every 1s)
│   ├── worker.py                # Async worker (executes jobs from queue)
│   └── db.py                   # SQLAlchemy models + SQLite connection
├── answers/                     # Reference implementation + setup guide
├── scaffold/                    # Guided track (fill-in-the-TODO version)
├── run_server.py                # Entry point (handles sys.path for Claude Desktop)
├── requirements.txt
├── PROMPT.md                    # Exercise spec + design questions
└── learningpoints_TaskScheduler.txt  # Debugging notes from integration
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Verify with MCP Inspector

```bash
npx @modelcontextprotocol/inspector python -m app.mcp_server
```

Opens a browser GUI (use **Chrome** — Safari blocks localhost cross-origin SSE). Steps:

1. Click **Connect** → 4 tools should appear
2. **task_create** → `description="test"`, `scheduled_at="2025-01-01T00:00:00"` → Run Tool → get `job_id`
3. Wait ~10s → **task_status** → `job_id: 1` → status should be `"completed"`
4. **task_create** with future time → **task_cancel** → status `"cancelled"`
5. **task_list** → see all jobs

## Connect to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "task-scheduler": {
      "command": "/absolute/path/to/chatgpt_task/.venv/bin/python",
      "args": ["/absolute/path/to/chatgpt_task/run_server.py"]
    }
  }
}
```

Restart Claude Desktop fully. The 🔨 icon in the chat input should show 4 tools.

> **Note:** Use `run_server.py` (not `-m app.mcp_server`) — Claude Desktop ignores the `cwd` field, so the script sets `sys.path` explicitly via absolute path.

## Connect to Claude Code

```bash
claude mcp add task-scheduler /absolute/path/to/.venv/bin/python /absolute/path/to/run_server.py
```

## Tech Stack

| Layer | Library |
|---|---|
| MCP framework | `mcp>=1.0.0` |
| ORM | SQLAlchemy 2.x |
| Database | SQLite |
| Async runtime | asyncio (stdlib) |

## Bonus Challenges (from PROMPT.md)

- Connect a real LLM to parse natural language task descriptions before `task_create`
- Add recurring job support (cron expressions)
- Add job chaining (Job A completes → triggers Job B)
- Expose job details as MCP `resources`
- Add a `daily_review` prompt template via MCP `prompts`
