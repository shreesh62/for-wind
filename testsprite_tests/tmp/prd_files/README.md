# Jarvis Assistant

A full-stack Jarvis-style AI assistant featuring voice interaction, automation plugins, proactive routines, remote APIs, and desktop/mobile dashboards. This document explains how to set up the development environment, run the system, package deliverables, and understand the architecture for future contributions.

---

## Quick Start

- **Clone & enter project**
  ```powershell
  git clone <repo-url>
  cd "JARVIS VERSIONS/for wind"
  ```
- **Create `.env`** (copy `example.env` when available) and provide API keys. Required variables today:
  ```env
  WEATHER_API_KEY=...
  PORCUPINE_ACCESS_KEY=...
  DISTANCEMATRIX_API_KEY=...
  GEOCODING_API_KEY=...
  GROQ_API_KEY=...
  REMOTE_API_KEY=choose-a-strong-token
  ```
- **Install Python dependencies**
  ```powershell
  python -m venv .venv
  .venv\Scripts\activate
  pip install --upgrade pip
  pip install -r requirements.txt  # or manual: pyinstaller, playwright, fastapi, uvicorn, websockets, psutil
  playwright install
  ```
- **Install JavaScript dependencies**
  ```powershell
  npm install --prefix desktop_app
  npm install --prefix mobile_dashboard
  ```
- **Run everything**
  ```powershell
  # Terminal 1 - Jarvis core
  python main.py

  # Terminal 2 - Electron desktop shell (development)
  npm start --prefix desktop_app

  # Terminal 3 - Mobile dashboard dev server
  npm run dev --prefix mobile_dashboard
  ```
  - Desktop UI opens automatically (Electron).
  - Mobile dashboard served at `http://127.0.0.1:5173/`.
  - Remote REST endpoints live at `http://127.0.0.1:8801/` requiring `X-API-Key: REMOTE_API_KEY`.

---

## Packaging & Distribution

- **Backend executable**
  ```powershell
  pip install pyinstaller
  pyinstaller jarvis_backend.spec
  ```
  - Output: `dist/jarvis-backend/` containing a standalone executable.

- **Desktop installer**
  ```powershell
  npm run dist --prefix desktop_app
  ```
  - Produces an NSIS installer under `desktop_app/dist/`.
  - Customize icons/config in `desktop_app/package.json` (`build` field).

- **Mobile dashboard**
  - Currently served via Vite dev server.
  - Production build: `npm run build --prefix mobile_dashboard` (outputs to `mobile_dashboard/dist/`).
  - Deploy via static hosting or embed in future mobile packaging.

---

## Project Structure

```
automation/              Playwright automation utilities (Gmail, WhatsApp, Instagram, etc.)
awareness/               System & window monitors (psutil, Windows accessibility)
config.py                Centralized settings loader (`get_settings()`)
core/                    Assistant orchestration, capability dispatcher, intent parsing, routine scheduler
memory/                  Short/long-term memory management
plugins/                 Capability plugins (manifest + module pattern)
server/                  FastAPI remote control server + static remote dashboard
ui/                      WebSocket-based desktop control surface
desktop_app/             Electron shell (main process + renderer)
mobile_dashboard/        Vite/React remote dashboard client
services/                External API services (weather, maps)
main.py                  JarvisAssistant entry point (voice loop, scheduling, remote server boot)
jarvis_backend.spec      PyInstaller recipe for backend bundling
```

---

## Core Services & Flows

- **Voice Loop (`main.py`)**
  - Wake word via Porcupine → microphone capture → command routing through `AssistantOrchestrator`.
  - Responses spoken via Edge-TTS (`edge_tts_voice.speak_edge`).
  - Keeps short-term memory and dispatches capabilities.

- **Capability Dispatch (`core/capability_dispatcher.py`)**
  - Evaluates user intent, triggers registered handlers (weather, maps, automation).
  - Plugins register additional handlers at runtime.

- **Automation (`automation/`)**
  - `playwright_manager.py` manages persistent browsers.
  - `gmail_actions.py` uses Playwright for compose/send.
  - `core/intent_parser.py` extracts structured parameters from natural language.

- **Remote Server (`server/app.py`)**
  - FastAPI app with `/health`, `/status`, `/commands` (API-key protected).
  - Serves static HTML remote dashboard at `/`.

- **Dashboards**
  - `ui/web_client/index.html`: WebSocket desktop UI for quick debugging.
  - Electron renderer (`desktop_app/renderer/`) wraps the UI in a native shell with status panels and manual command input.
  - React/Vite mobile dashboard polls `/status` and allows remote commands.

- **Proactive Routines**
  - `core/routine_scheduler.py` schedules tasks (daily briefing, battery reminders).
  - Integrated in `main.JarvisAssistant` with voice + alert outputs.

---

## Onboarding Checklist

- **1. Install prerequisites**: Python 3.10+, Node.js 18+, npm, Git, Mic & speakers, Porcupine `.ppn` wake-word file (already in `wake_words/`).
- **2. Populate `.env`** with API keys. For Groq/Weather/Maps/Porcupine, follow provider documentation.
- **3. Run dependency installs** (pip/npm commands above).
- **4. Test voice pipeline**: Start Jarvis, say “Jarvis, what’s the weather in <city>?”. Confirm voice response+UI updates.
- **5. Test automation**: “Send email to test@example.com about project update body see you tomorrow.” Playwright browser should compose email after login.
- **6. Verify dashboards**: Electron UI, web UI (`ui/web_client/index.html` served via WebSocket), remote dashboard at `http://127.0.0.1:8801/`, mobile Vite app.
- **7. Validate packaging**: Build backend executable + desktop installer to ensure distribution pipeline works end-to-end.

---

## Troubleshooting

- **`npm` not found**: Install Node.js and reopen terminal. Use `npm --version` to verify.
- **Execution policy blocks npm.ps1** (PowerShell): Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` or use an elevated Command Prompt.
- **PyInstaller missing modules**: Ensure `pip install -r requirements.txt` ran in the same environment; re-run with `--hidden-import` if plugins added later.
- **Playwright login required**: First automation run opens Chromium. Manually log in once (credentials stored in `automation/storage/`).
- **Porcupine fails**: Check `.env` for `PORCUPINE_ACCESS_KEY`, confirm wake-word `.ppn` path matches (`wake_words/jarvis_en_windows.ppn`).
- **FastAPI errors**: Make sure `REMOTE_API_KEY` is set and included as `X-API-Key` header. Install dependencies (`fastapi`, `uvicorn`, `websockets`).
- **High CPU**: Playwright/Chromium can spike resources; ensure headless mode is appropriate or close unused sessions.

---

## Contributing

- **Code style**: Follow existing formatting; use type hints where possible.
- **Plugins**: Add `manifest.json` and `module.py`, register capabilities via `PluginLoader` runtime. Ensure patterns are specific to avoid misfires.
- **Testing**: Introduce unit tests in a `tests/` directory (PyTest recommended) and use mock services for external APIs.
- **Docs**: Update `README.md` and inline docstrings whenever adding new modules or build steps.

---

## Roadmap Ideas

- **Enhanced onboarding**: GUI wizard for API keys, default routine scheduling.
- **Mobile deployment**: Package React app into native wrapper (React Native / Capacitor) for push notifications.
- **Advanced automation**: Gmail inbox digests, calendar integration, Windows/MacOS app control modules.
- **Personality & emotion**: Sentiment-driven responses, configurable voice skins.
- **Telemetry & logging**: Persist conversation/system logs for analytics; optional cloud sync.

---

## Support

- **Issues**: File GitHub issues or contact maintainer.
- **Logs**: Check console output from `main.py`, Electron dev tools, or FastAPI logs for diagnostics.
- **Community**: Share automation ideas and plugins; Jarvis is built to be extendable.

Enjoy building with Jarvis! 🚀
