"""Launch FRIDAY — the one command you run to start the system.

    python start_friday.py

This starts the full FRIDAY API server with:
- Kernel execution enabled (cognitive kernel with event log, suspension, memory)
- NVIDIA model router with per-model failover and circuit breaker
- Memory system (7 tiers: working, episodic, procedural, semantic, failure,
  capability, preference)
- Permission gate (Ch 35 safety boundary)
- Reactive loop (recovery, competence, reflection)
- Browser controller (CDP on your real Chrome when available, fresh Chromium
  otherwise)

The API is at http://127.0.0.1:8801 with docs at http://127.0.0.1:8801/docs.
Send commands via POST /api/command with your REMOTE_API_KEY.

To connect to your real Chrome (with logins): start Chrome with
  chrome --remote-debugging-port=9222
before running this script.

Rollback: set FRIDAY_USE_KERNEL_EXECUTION=0 to route goals through the legacy
Operator path without the kernel. No code change needed.
"""

import os
import sys

# Ensure UTF-8 output on Windows consoles
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# The kernel path is the production default
os.environ.setdefault("FRIDAY_USE_KERNEL_EXECUTION", "1")

from friday.api.server import start_server

if __name__ == "__main__":
    host = os.getenv("FRIDAY_HOST", "127.0.0.1")
    port = int(os.getenv("FRIDAY_PORT", "8801"))
    start_server(host=host, port=port)
