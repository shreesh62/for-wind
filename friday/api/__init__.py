"""API layer — FastAPI backend for desktop and mobile clients.

Single API consumed by both:
- Tauri desktop app (local, via localhost)
- Mobile app (remote, authenticated)

Endpoints:
- POST /api/command — Execute command (JARVIS/FRIDAY routing)
- GET /api/status — System status + active goal + memory/model stats
- POST /api/memory/search — Search memory by query
- GET /api/memory/recent — Recent interaction history
- GET /api/models — Available models + usage stats
- WS /api/ws — WebSocket for real-time updates
- GET /api/health — Health check (no auth)

Auth: API key via X-API-Key header (REST) or ?token= (WebSocket)
Docs: Auto-generated at /docs (OpenAPI/Swagger)
"""

from friday.api.app import create_friday_api

__all__ = ["create_friday_api"]
