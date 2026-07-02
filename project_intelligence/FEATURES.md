# Feature Inventory

Status key:
- Working: implemented and plausibly used by the runtime.
- Partial: exists but incomplete, gated, or missing deps.
- Experimental: test/probe scripts, unclear integration.
- Planned: capability definitions exist but handlers missing or disabled.
- Deprecated: snapshot/legacy path exists but is replaced.
- Broken: evidence suggests it cannot work as-is (missing deps, disabled path, etc.).
- Unknown: not enough evidence.

Confidence: Medium overall (some features depend on runtime environment and external APIs).

## Primary Features (User-Facing)

| Feature | Status | Completion % | Stability | Dependencies | Notes |
|---|---:|---:|---|---|---|
| Voice command loop | Working | 75 | Medium | `main.py`, `jarvis_io.py`, `SpeechRecognition`, mic device | Gated by `DISABLE_MIC`; behavior depends on local audio stack |
| Wake word (Porcupine) | Working | 80 | Medium | `pvporcupine`, `PyAudio`, `wake_words/*.ppn`, `.env:PORCUPINE_ACCESS_KEY` | Graceful fallback if deps/key missing |
| Text-to-speech (Edge TTS) | Working | 80 | Medium | `edge-tts`, `edge_tts_voice.py` | Controlled by `DISABLE_TTS`; fallback paths may exist |
| Personality formatting | Working | 60 | Medium | `personality.py`, `tts_formatter.py` | Affects output style; does not change core logic |
| Capability registry + intent matching | Working | 75 | Medium | `capabilities.py`, `config/capabilities.json` | Regex-based intent matching; plugins can add/override |
| Weather queries | Working | 60 | Medium | `services/weather_service.py`, `.env:WEATHER_API_KEY` | External API required |
| Maps distance/time | Working | 55 | Medium | `services/maps_service.py`, `.env:DISTANCEMATRIX_API_KEY`, `.env:GEOCODING_API_KEY` | External APIs required |
| News brief | Working | 45 | Medium-Low | `services/news_service.py`, `.env:NEWS_API_KEY?` | `NEWS_API_KEY` referenced in config; confirm service implementation |
| Remote control server | Working | 75 | Medium | `server/app.py`, `fastapi`, `uvicorn`, `.env:REMOTE_API_KEY` | Endpoints: `/health`, `/status`, `/commands`, `/execute`, plus static dashboard |
| Remote webhook relay (HMAC) | Working | 70 | Medium | `remote/webhook_server.py`, `fastapi`, `requests`, `.env:WEBHOOK_SECRET` | Forwards to local `/execute`; includes rate limit + replay protection |
| Telegram relay | Working | 60 | Medium | `remote/telegram_relay.py`, `python-telegram-bot`, `.env:TELEGRAM_BOT_TOKEN` | Forwards to `/execute` with API key |
| Desktop UI (Electron shell) | Working | 65 | Medium | `desktop_app/*`, `ui/*`, `websockets`, `electron` | Electron bundles `ui/` as resources |
| Mobile dashboard (React/Vite) | Working | 55 | Medium | `mobile_dashboard/*`, Vite, React | Talks to remote server; production deploy not fully specified |

## Automation Features (Action Layer)

| Feature | Status | Completion % | Stability | Dependencies | Notes |
|---|---:|---:|---|---|---|
| Desktop screenshot capture | Working | 70 | Medium | `automation/services.py`, `PIL.ImageGrab` | Stores under `screenshots/` (runtime artifact) |
| Desktop OCR (region) | Partial | 45 | Low-Medium | `pytesseract`, `pillow`, `automation/services.py` | Requires local Tesseract install/config; integration uncertain |
| Focus window | Working | 60 | Medium | `automation/desktop_actions.py`, Windows APIs | Used by dispatcher and planner |
| Type text | Working | 60 | Medium | `pyautogui` | Needs correct focus + verification to avoid illusion |
| Click / scroll | Working | 55 | Medium-Low | `pyautogui`, UIA snapshotting | Hard to verify reliably; depends on verification coverage |
| App launch | Working | 60 | Medium | `automation/services.py` uses `subprocess.Popen` | Windows-specific app command mapping table exists |
| Website navigation (non-Chrome) | Partial | 40 | Low-Medium | `webbrowser`, `automation/services.py` | Chrome path explicitly disabled in `open_website()`; expects new pipeline |
| Chrome open + unlock (taskbar-anchored) | Partial | 55 | Medium-Low | `automation/chrome_pipeline.py`, `automation/taskbar_*`, `cv2`, `numpy`, `pyautogui`, `pytesseract`, DPAPI vault | Not all deps are pinned in requirements (notably `opencv-python`) |
| Browser active-tab summary via DevTools | Working | 60 | Medium | `automation/devtools_bridge.py`, Chrome remote debugging | Requires Chrome started with `--remote-debugging-port` and attach success |
| WhatsApp message automation | Working | 50 | Medium-Low | `automation/quick_actions.py` + Playwright profile | Needs persistent login in Playwright storage/profile |
| Instagram DM automation | Working | 50 | Medium-Low | Playwright | Same auth issues as WhatsApp |
| Gmail automation | Partial | 40 | Low-Medium | `automation/gmail_actions.py` / templates | Login flows fragile; legacy vs cognitive integration unclear |
| Amazon search automation | Working | 55 | Medium-Low | Playwright | Dependent on site UX changes and auth |
| YouTube search and click-first | Working | 50 | Medium-Low | `core/capability_dispatcher.py`, `automation/services.py` | Uses navigation + click; verification uncertain |

## Cognitive System Features (Reasoning/Feedback)

| Feature | Status | Completion % | Stability | Dependencies | Notes |
|---|---:|---:|---|---|---|
| Cognitive routing (COGNITIVE_MODE=1) | Partial | 60 | Medium | `core/assistant.py`, `automation/cognitive_loop.py` | Current code appears strict/no fallback; test carefully |
| Goal parsing | Partial | 50 | Medium-Low | `automation/goal_parser.py`, `automation/goal_schema.py` | Coverage of intents unknown |
| Task graph planning | Partial | 55 | Medium-Low | `automation/task_graph.py`, `automation/action_planner.py` | Requires robust perception inputs |
| Semantic verification | Partial | 55 | Medium | `automation/verification.py` | Some verification functions exist; must ensure all action paths use them |
| Self-repair engine | Partial | 50 | Medium-Low | `core/self_repair.py`, `core/repair_*` | Depends on diagnostics quality and stable perception snapshots |
| UI pattern memory (learned actions) | Partial | 45 | Medium-Low | `automation/ui_pattern_memory.py`, `ui_patterns.json`, `memory/ui_memory.json` | Evidence of 1 recorded pattern in `ui_patterns.json` |
| Credential vault (DPAPI) | Working | 70 | Medium | `security/credential_vault.py`, `pywin32` | Windows-only; secure-by-design (no values in LLM/logs) |
| Training mode for UI anchors/logins | Partial | 50 | Medium-Low | `core/training_controller.py`, taskbar trainer | Several training flows marked OBSOLETE; new taskbar training is primary |

## Experimental / Planned / Deprecated

| Feature | Status | Completion % | Stability | Dependencies | Notes |
|---|---:|---:|---|---|---|
| OCR ROI change detection | Experimental | 20 | Low | `mss`, `cv2`, `pytesseract` | `roi_change_ocr.py` + related tests; deps not pinned |
| CLIP-based screen classification | Experimental | 10 | Low | `clip`, `torch` | `clip_test.py`; not integrated |
| Agent framework (PydanticAI) | Experimental | 10 | Low | `pydantic_ai` | `test_pydantic_ai.py`; not pinned |
| "send_email" capability | Planned | 20 | Low | registry + planner/automation | Capability exists as planned in config; verify handler presence |
| "open_browser" and "play_music" capabilities | Planned | 10 | Low | registry | Defined as planned; handlers likely missing |
| Legacy Chrome open paths | Deprecated | 30 | Low | `automation/services.py` | Explicitly disabled in `open_website()`; superseded by `chrome_pipeline.py` |

