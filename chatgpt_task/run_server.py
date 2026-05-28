import sys
import os

# Ensure the project root is on sys.path regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from app.mcp_server import _main

asyncio.run(_main())
