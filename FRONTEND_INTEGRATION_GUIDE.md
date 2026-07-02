# FRIDAY — Frontend Integration Guide

Everything a frontend engineer needs to build a client (desktop, mobile, web)
against the FRIDAY backend. The backend contains ALL business logic.
Frontends are thin clients that consume these APIs.

**Version**: 0.1.0
**Base URL (local)**: `http://127.0.0.1:8801`
**WebSocket**: `ws://127.0.0.1:8801/api/ws`
**Interactive docs**: `http://127.0.0.1:8801/docs` (Swagger UI, auto-generated)
**OpenAPI spec**: `http://127.0.0.1:8801/openapi.json`

---

## 1. Starting the Backend

```bash
python -m friday.api.server
```

Environment (`.env`):
- `REMOTE_API_KEY` — API key clients must send (required for auth)
- `NVIDIA_API_KEY` — NVIDIA NIM inference (primary models)
- `GROQ_API_KEY` — Groq inference (fallback)
- `FRIDAY_HOST` (default `127.0.0.1`), `FRIDAY_PORT` (default `8801`)

---

## 2. Authentication

### REST
Send the API key in the `X-API-Key` header on every request except `/api/health`.

```
X-API-Key: <REMOTE_API_KEY>
```

Missing/invalid key → `401 Unauthorized`:
```json
{ "detail": "Invalid API key" }
```

### WebSocket
Pass the key as a query parameter:
```
ws://127.0.0.1:8801/api/ws?token=<REMOTE_API_KEY>
```
Invalid token → connection closed with code `4001`.

---

## 3. Core Concept: JARVIS vs FRIDAY Modes

Every command is classified into a mode + complexity level:

| Mode | Meaning | Complexity Levels |
|------|---------|-------------------|
| **JARVIS** | Assistant — fast conversational answer | 0 (question) |
| **FRIDAY** | Agent — perceive/plan/act/verify | 1 (simple action), 2 (multi-step), 3 (complex goal) |

The frontend does NOT decide the mode — the backend classifies it.
The frontend should display the returned `mode` and `complexity` to the user
(e.g., 🧠 for JARVIS, ⚡ for FRIDAY).

Wake words override classification: send `wake_word: "jarvis"` or `"friday"`.

---

## 4. REST Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| /api/health | GET | no | Connectivity check |
| /api/command | POST | yes | Execute command (JARVIS/FRIDAY) |
| /api/status | GET | yes | System status + stats |
| /api/worldstate | GET | yes | Live perception snapshot |
| /api/memory/search | POST | yes | Search memory |
| /api/memory/recent | GET | yes | Interaction history |
| /api/memory/remember | POST | yes | Store semantic fact |
| /api/models | GET | yes | Models + usage |
| /api/tasks/current | GET | yes | Task monitoring |
| /api/ws | WS | token | Real-time events |

### GET /api/health
No auth. Connectivity check.

**Response** `200`:
```json
{ "status": "ok", "version": "0.1.0", "uptime": 42.5 }
```

---

### POST /api/command
Execute a command through JARVIS/FRIDAY routing.

**Request**:
```json
{
  "text": "What is Python?",
  "wake_word": null,
  "speak": false,
  "metadata": {}
}
```
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| text | string | yes | The command or question |
| wake_word | string\|null | no | "jarvis" or "friday" to force mode |
| speak | bool | no | Speak response via TTS (server-side) |
| metadata | object | no | Arbitrary context |

**Response** `200`:
```json
{
  "ok": true,
  "text": "Python is a programming language.",
  "mode": "jarvis",
  "complexity": 0,
  "handled": true,
  "verified": null,
  "duration_ms": 2740.5,
  "error": null
}
```
| Field | Type | Notes |
|-------|------|-------|
| ok | bool | False if an error occurred |
| text | string | Response to show/speak |
| mode | string | "jarvis" or "friday" |
| complexity | int | 0-3 |
| handled | bool | Whether a response was produced |
| verified | bool\|null | FRIDAY actions only: outcome backed by evidence |
| duration_ms | float | Processing time |
| error | string\|null | Present when ok=false |

---

### GET /api/status
Full system status.

**Response** `200`:
```json
{
  "online": true,
  "mode": "idle",
  "active_goal": null,
  "uptime_seconds": 120.3,
  "memory_stats": {
    "working": { "turns": 3, "has_goal": false },
    "episodic": { "total_episodes": 12, "success_rate": 0.83 },
    "procedural": { "total_patterns": 4, "total_successes": 9, "action_types": {}, "repair_outcomes": 2 },
    "semantic": { "total_facts": 7, "has_embeddings": true }
  },
  "model_stats": {
    "total_requests": 15,
    "total_tokens": 2400,
    "avg_latency_ms": 2600.0,
    "failure_rate": 0.0,
    "by_provider": { "nvidia": 14, "groq": 1 }
  }
}
```

---

### POST /api/memory/search
Search memory across tiers.

**Request**:
```json
{ "query": "chrome", "top_k": 5, "tier": null }
```
`tier`: `"episodic"`, `"procedural"`, `"semantic"`, or `null` (all).

**Response** `200`:
```json
{
  "results": [
    {
      "content": "User: Open Chrome\nAssistant: Chrome opened",
      "tier": "episodic",
      "timestamp": 1780000000.0,
      "tags": ["friday"],
      "metadata": { "action_type": "open_app", "success": true }
    }
  ]
}
```

---

### GET /api/memory/recent?limit=10
Recent interaction history.

**Response** `200`:
```json
{
  "episodes": [
    { "user": "Hi", "assistant": "Hello!", "mode": "jarvis", "timestamp": 1780000000.0, "success": null }
  ]
}
```

---

### POST /api/memory/remember
Store a durable fact in semantic memory.

**Request**:
```json
{ "content": "Shreesh prefers DOM over screenshots", "category": "preference" }
```
`category`: general | user | app | site | preference

**Response** `200`:
```json
{ "ok": true, "stored": "Shreesh prefers DOM over screenshots" }
```

---

### GET /api/models
Available models, providers, and usage.

**Response** `200`:
```json
{
  "providers": ["nvidia", "groq"],
  "models": [
    { "provider": "nvidia", "model_id": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
      "capabilities": ["reasoning", "conversation", "summarization", "classification"], "priority": 9 }
  ],
  "usage": { "total_requests": 15, "by_provider": { "nvidia": 14 } }
}
```

---

### GET /api/tasks/current
Monitor the currently executing FRIDAY task.

**Response** `200` (idle):
```json
{ "active": false, "task": null }
```

**Response** `200` (active):
```json
{
  "active": true,
  "task": {
    "goal": "Research laptops and build a spreadsheet",
    "total_steps": 5,
    "completed_steps": 2,
    "progress": 0.4,
    "is_complete": false,
    "current_step": 2,
    "steps": [
      { "order": 0, "action_type": "open_app", "target": "chrome",
        "description": "Open browser", "status": "completed", "result": "Done" }
    ]
  }
}
```

---

### GET /api/worldstate
Get a fresh perception snapshot — what FRIDAY currently perceives.
The planner reasons on this, never raw pixels (ADR-014).

**Response** `200`:
```json
{
  "timestamp": 1781026217.4,
  "window": "Google Chrome",
  "app": "chrome.exe",
  "cursor": [1334, 893],
  "focused": "Search box",
  "ui_elements": 12,
  "ocr_regions": 0,
  "browser_url": "https://google.com",
  "browser_title": "Google",
  "browser_elements": 45,
  "derived": { "login": false, "error": false, "loading": false, "modal": false },
  "state_hash": "abb9c3a7af7e79b4",
  "sources": ["process", "uia", "browser", "screen"],
  "semantic_coverage": 0.95
}
```
`semantic_coverage` (0-1): fraction of perception that is semantic (DOM/UIA)
vs visual (OCR). Higher = more reliable for action targeting.

---

## 5. WebSocket — Real-Time Events

Connect: `ws://127.0.0.1:8801/api/ws?token=<API_KEY>`

All messages use the envelope: `{ "type": "<event>", "data": { ... } }`

### Client → Server
```json
{ "type": "command", "text": "What is Python?", "wake_word": null }
{ "type": "ping" }
```

### Server → Client
| type | When | data |
|------|------|------|
| `command_response` | Reply to a WS command | `{ ok, text, mode, complexity }` |
| `command_completed` | Any command finished (broadcast) | full CommandResponse |
| `notification` | System notification | `{ message, level }` |
| `pong` | Reply to ping | `{}` |

Example flow:
```javascript
const ws = new WebSocket(`ws://127.0.0.1:8801/api/ws?token=${apiKey}`);
ws.onopen = () => ws.send(JSON.stringify({ type: "command", text: "What is Python?" }));
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === "command_response") console.log(msg.data.text);
};
```

---

## 6. WorldState Structure (Perception)

The planner reasons on WorldState, never raw pixels (ADR-014). When exposed
via API, WorldState serializes as:

```json
{
  "timestamp": 1780000000.0,
  "window": "Google Chrome",
  "app": "chrome.exe",
  "cursor": [500, 300],
  "focused": "Search box",
  "ui_elements": 12,
  "ocr_regions": 3,
  "browser_url": "https://google.com",
  "browser_title": "Google",
  "browser_elements": 45,
  "derived": { "login": false, "error": false, "loading": false, "modal": false },
  "state_hash": "a1b2c3d4e5f6g7h8",
  "sources": ["process", "uia", "browser", "screen"],
  "semantic_coverage": 0.95
}
```

`semantic_coverage` (0-1): how much perception is semantic (DOM/UIA) vs visual (OCR).
Higher = more reliable.

---

## 7. Memory Structure

Four tiers (Memory OS blueprint):

| Tier | Contents | Persistence |
|------|----------|-------------|
| **working** | Current session: conversation buffer, active goal | Volatile |
| **episodic** | Interaction history with success tracking | Persistent (JSON) |
| **procedural** | Learned action patterns + repair strategies | Persistent |
| **semantic** | Facts + NVIDIA embeddings (semantic search) | Persistent |

---

## 8. Agent Status Structure

`active_goal` in /api/status reflects working memory. When FRIDAY executes a
multi-step goal, poll `/api/tasks/current` for live progress, or subscribe to
`task_progress` WebSocket events (when wired by the executor).

---

## 9. Error Formats

FastAPI standard:
```json
{ "detail": "Invalid API key" }       // 401
{ "detail": "Memory not initialized" } // 503
```

Command-level errors return `200` with `ok: false`:
```json
{ "ok": false, "text": "", "error": "Action failed: ...", "mode": "friday", "complexity": 1 }
```

Validation errors (`422`) follow FastAPI's schema:
```json
{ "detail": [ { "loc": ["body", "text"], "msg": "field required", "type": "value_error.missing" } ] }
```

---

## 10. Screenshot & Notification Interfaces (planned contracts)

These are defined in schemas and reserved for when the executor wires them:

- **Screenshots**: `screenshot` WebSocket event with base64 JPEG data URL
  `{ "type": "screenshot", "data": { "image": "data:image/jpeg;base64,...", "timestamp": ... } }`
- **Notifications**: `notification` WebSocket event
  `{ "type": "notification", "data": { "message": "...", "level": "info|warn|error" } }`

Frontends should handle these event types even before they're emitted.

---

## 11. Recommended Frontend Architecture

```
Frontend (desktop/mobile/web)
  ├── API client (wraps REST + WebSocket)   ← no business logic
  ├── Auth: store API key securely
  ├── Command input → POST /api/command
  ├── Live updates → WebSocket subscription
  ├── Status panel → poll GET /api/status (every ~10s)
  └── Memory view → GET /api/memory/recent, POST /api/memory/search
```

A reference TypeScript client exists at `desktop_tauri/src/api.ts` (frozen
scaffold — use as contract reference only, not as a maintained component).

---

## 12. Quick Start Checklist for Frontend Engineers

1. Start backend: `python -m friday.api.server`
2. Open `http://127.0.0.1:8801/docs` to explore all endpoints interactively
3. Get `REMOTE_API_KEY` from the user / `.env`
4. Implement API client: health check → command → WebSocket
5. Display `mode` + `complexity` from command responses
6. Poll `/api/status` for the status panel
7. Handle WebSocket event types (including reserved screenshot/notification)
8. All logic stays server-side — keep the frontend thin
