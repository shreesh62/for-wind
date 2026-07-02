import os
import time
from queue import Queue

# HARD GUARD: this legacy remote server can drive the old action paths.
# Refuse to start unless explicitly authorized (anti-phantom-actions).
if os.getenv("FRIDAY_ALLOW_LEGACY_MAIN", "").strip().lower() not in ("1", "true", "yes"):
    print(
        "[BLOCKED] Legacy start_remote_server.py will not start.\n"
        "Set FRIDAY_ALLOW_LEGACY_MAIN=1 only if you truly intend to run it."
    )
    raise SystemExit(0)

from server.app import RemoteServer

queue = Queue()
server = RemoteServer(queue, api_key="jarvis")
server.start()
print("Remote server running on http://127.0.0.1:8801 with API key 'jarvis'")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    server.stop()