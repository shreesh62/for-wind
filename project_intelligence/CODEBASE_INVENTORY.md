# Codebase Inventory

This inventory excludes heavy/generated directories by default: .git, .pytest_cache, .venv, .venv312, __pycache__, build, dist, friday_env, logs, node_modules, screenshots, tts_output.
Folders with " - Copy" are treated as snapshots/duplicates and excluded from deep indexing.

| File Path | Purpose | Dependencies | Status | Risk Level | Notes |
|---|---|---|---|---|---|
| .env |  |  | Unknown | Unknown |  |
| .env.example |  |  | Unknown | Unknown |  |
| .gitignore |  |  | Unknown | Unknown |  |
| automation/__init__.py | Automation scripts and Playwright flows for Jarvis. |  | Unknown | High |  |
| automation/action_planner.py | Action planner: Generate semantic action plans from state gaps. | __future__, awareness.world_state, semantic_actions, typing, ui_pattern_memory | Unknown | High |  |
| automation/amazon_shopping.py | Amazon shopping automation leveraging Playwright-managed Chrome profile. | __future__, asyncio, playwright_manager, quick_actions, typing | Unknown | High |  |
| automation/browser_state_tracker.py | Browser state tracker emitting awareness events via DevToolsBridge. | __future__, asyncio, awareness.event_dispatcher, awareness.types, devtools_bridge, os, playwright_manager, threading ... | Unknown | High |  |
| automation/chrome_pipeline.py | Chrome open + unlock pipeline using taskbar-anchored visual system. | PIL, __future__, automation.taskbar_locator, cv2, getpass, numpy, pyautogui, pytesseract ... | Unknown | High |  |
| automation/cognitive_loop.py | Cognitive control loop: The core perception-reasoning-action-verification cycle. | __future__, action_planner, automation.chrome_pipeline, awareness.perception_snapshot, awareness.world_state, cognitive_loop_task_graph, core.repair_diagnostics, core.repair_strategies ... | Unknown | High |  |
| automation/cognitive_loop_task_graph.py | Task graph execution methods for cognitive loop. | __future__, automation.goal_schema, automation.state_gap_analyzer, automation.task_graph, awareness.perception_snapshot, typing | Unknown | High |  |
| automation/desktop_actions.py | Desktop automation utilities built on top of PyAutoGUI and Pywinauto. | PIL, __future__, ctypes, cv2, dataclasses, datetime, easyocr, mss ... | Unknown | High |  |
| automation/devtools_bridge.py | Chrome DevTools bridge for direct DOM introspection and control. | __future__, asyncio, dataclasses, json, os, playwright_manager, typing, websockets | Unknown | High |  |
| automation/element_resolver.py | Semantic element resolver with multi-signal ranking. | __future__, awareness.perception_snapshot, difflib, security.credential_vault, typing | Unknown | High |  |
| automation/error_models.py | Error models: Classification and handling of action failures. | __future__, dataclasses, enum, semantic_actions, typing | Unknown | High |  |
| automation/gmail_actions.py | Playwright-driven Gmail automation helpers. | __future__, asyncio, dataclasses, playwright_manager | Unknown | High |  |
| automation/goal_parser.py | Goal parser: Convert natural language into formal Goal objects. | __future__, goal_schema, re, typing | Unknown | High |  |
| automation/goal_schema.py | Goal schema: Formal representation of user intent. | __future__, awareness.world_state, dataclasses, typing | Unknown | High |  |
| automation/planner.py | High-level automation planner that maps natural-language commands to actions. | __future__, automation.services, awareness.snapshot, awareness.state_cache, capabilities, cognitive_loop, re, time ... | Unknown | High |  |
| automation/playwright_manager.py | Playwright automation manager for web app control. | __future__, asyncio, contextlib, os, pathlib, playwright.async_api, shutil, socket ... | Unknown | High |  |
| automation/quick_actions.py | User-facing automation actions orchestrated via Playwright. | __future__, asyncio, dataclasses, playwright_manager, typing | Unknown | High |  |
| automation/semantic_actions.py | Semantic actions: High-level actions that operate on perceived world state. | __future__, dataclasses, typing | Unknown | High |  |
| automation/services.py | High-level automation service functions for Jarvis. | PIL, __future__, amazon_shopping, asyncio, automation.timing, awareness.state_cache, awareness.world_state, core.telemetry ... | Unknown | High |  |
| automation/state_gap_analyzer.py | State gap analyzer: Identify missing states between current world and goal. | __future__, awareness.world_state, goal_schema, typing | Unknown | High |  |
| automation/storage/google_calendar.json | Automation subsystem file. |  | Unknown | High |  |
| automation/task_graph.py | Dynamic task graph for intent-driven action planning. | __future__, automation.semantic_actions, awareness.perception_snapshot, dataclasses, enum, typing | Unknown | High |  |
| automation/taskbar_locator.py | Human-style visual taskbar locator. | PIL, __future__, automation.taskbar_trainer, cv2, json, numpy, os, pathlib ... | Unknown | High |  |
| automation/taskbar_trainer.py | Human-style visual taskbar detection system. | PIL, __future__, ctypes, cv2, json, numpy, os, pathlib ... | Unknown | High |  |
| automation/timing.py | State-based timing utilities for cognitive loop. | __future__, time, typing | Unknown | High |  |
| automation/ui_pattern_memory.py | UI pattern memory: Learn from successful UI interactions. | __future__, awareness.world_state, dataclasses, json, pathlib, time, typing | Unknown | High |  |
| automation/verification.py | Semantic verification engine for action postconditions. | __future__, typing | Unknown | High |  |
| awareness/__init__.py | Awareness modules for screen, system, and environment monitoring. |  | Unknown | High |  |
| awareness/controller.py | Coordinator for awareness monitors and shared state. | __future__, event_dispatcher, process_watcher, state_cache, types, typing, windows.uia_monitor | Unknown | High |  |
| awareness/event_dispatcher.py | Simple event dispatcher that funnels awareness events to subscribers. | __future__, collections, threading, types, typing | Unknown | High |  |
| awareness/perception_snapshot.py | Unified perception snapshot for cognitive system. | __future__, dataclasses, hashlib, time, typing | Unknown | High |  |
| awareness/process_watcher.py | Process watcher emitting awareness events for process lifecycle changes. | __future__, dataclasses, psutil, threading, time, types, typing | Unknown | High |  |
| awareness/snapshot.py | Awareness/perception subsystem file. | __future__, time, types, typing | Unknown | High |  |
| awareness/state_cache.py | Shared state cache for awareness data. | __future__, copy, pyautogui, snapshot, threading, time, types, typing ... | Unknown | High |  |
| awareness/system_monitor.py | System monitoring utilities for Jarvis. | __future__, dataclasses, platform, psutil, typing | Unknown | High |  |
| awareness/types.py | Shared types and dataclasses for the awareness subsystem. | __future__, dataclasses, enum, typing | Unknown | High |  |
| awareness/windows/uia_monitor.py | Windows UI Automation monitor for continuous screen awareness. | __future__, dataclasses, platform, threading, time, types, typing, uiautomation | Unknown | High |  |
| awareness/windows_accessibility.py | Windows accessibility monitoring utilities. | __future__, ctypes, dataclasses, platform, psutil, typing | Unknown | High |  |
| awareness/world_state.py | WorldState: Single source of truth for machine perception. | __future__, dataclasses, hashlib, time, typing | Unknown | High |  |
| capabilities.py |  | copy, json, pathlib, re, typing | Unknown | Unknown |  |
| clip_test.py |  | PIL, clip, torch | Experimental | Unknown |  |
| COGNITIVE_SYSTEM_COMPLETE.md | Documentation. |  | Working | Low-Medium |  |
| config.py | Central configuration for Jarvis assistant. | dataclasses, dotenv, functools, os, pathlib | Unknown | Unknown |  |
| config/__init__.py | Configuration package providing access to static resources and settings. | __future__, dataclasses, dotenv, functools, os, pathlib | Unknown | Unknown |  |
| config/capabilities.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| core/__init__.py | Core orchestration package for the Jarvis assistant. |  | Unknown | High |  |
| core/assistant.py | Assistant orchestrator coordinating memory, automation, and dialogue. | __future__, asyncio, automation.cognitive_loop, automation.planner, automation.services, awareness.snapshot, awareness.state_cache, core.capability_dispatcher ... | Unknown | High |  |
| core/capability_dispatcher.py | Capability dispatcher mapping intents to concrete handlers. | __future__, automation.services, capabilities, core.telemetry, dataclasses, re, services.news_service, typing ... | Unknown | High |  |
| core/focus_watcher.py | Focus-triggered passive capture system for training mode. | __future__, awareness.perception_snapshot, awareness.state_cache, time, typing | Unknown | High |  |
| core/intent_parser.py | Utility functions for extracting structured intents from natural language. | __future__, dataclasses, re, typing | Unknown | High |  |
| core/llm_sanitizer.py | LLM input sanitizer to prevent credential leakage. | __future__, re, typing | Unknown | High |  |
| core/reasoner.py | Lightweight reasoning helpers to determine execution routes for commands. | __future__, awareness.state_cache, capabilities, dataclasses, os, typing | Unknown | High |  |
| core/repair_diagnostics.py | Failure detection and diagnosis engine for self-repair system. | __future__, awareness.perception_snapshot, typing | Unknown | High |  |
| core/repair_strategies.py | Repair strategy engine for self-repair system. | __future__, awareness.perception_snapshot, typing | Unknown | High |  |
| core/repair_telemetry.py | Repair telemetry logging system. | __future__, json, pathlib, time, typing | Unknown | High |  |
| core/routine_scheduler.py | Background scheduler for Jarvis proactive routines. | __future__, dataclasses, datetime, threading, time, typing | Unknown | High |  |
| core/self_repair.py | Self-repair system for cognitive loop. | __future__, automation.semantic_actions, automation.task_graph, awareness.perception_snapshot, core.repair_diagnostics, core.repair_strategies, core.repair_telemetry, dataclasses ... | Unknown | High |  |
| core/telemetry.py | Lightweight telemetry logger for Jarvis. | __future__, collections, json, pathlib, time, typing | Unknown | High |  |
| core/training_controller.py | Training controller for learning login flows and authentication patterns. | __future__, automation.taskbar_trainer, automation.ui_pattern_memory, awareness.controller, awareness.perception_snapshot, awareness.state_cache, core.focus_watcher, getpass ... | Unknown | High |  |
| desktop_app/main.js | Electron desktop shell file. |  | Unknown | Medium |  |
| desktop_app/package-lock.json | Electron desktop shell file. |  | Unknown | Medium |  |
| desktop_app/package.json | Electron desktop shell file. |  | Unknown | Medium |  |
| desktop_app/renderer/index.html | Electron desktop shell file. |  | Unknown | Medium |  |
| desktop_app/renderer/renderer.js | Electron desktop shell file. |  | Unknown | Medium |  |
| desktop_app/renderer/style.css | Electron desktop shell file. |  | Unknown | Medium |  |
| e2e/example.spec.ts |  |  | Experimental | Unknown |  |
| edge_temp.wav |  |  | Unknown | Unknown |  |
| edge_tts_alt.py |  |  | Unknown | Unknown |  |
| edge_tts_voice.py |  | asyncio, edge_tts, os, playsound, re, subprocess, sys, tempfile ... | Unknown | Unknown |  |
| groq_jarvis.py |  |  | Unknown | Unknown |  |
| groq_llm.py |  | config, groq, os, re, time | Unknown | Unknown |  |
| interaction_log.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| jarvis_ai/.gitattributes |  |  | Unknown | Unknown |  |
| jarvis_ai/README.md | Documentation. |  | Working | Low-Medium |  |
| jarvis_backend.spec |  |  | Unknown | Unknown |  |
| jarvis_io.py |  | distutils.version, os, packaging.version, pyttsx3, queue, setuptools._distutils.version, speech_recognition, subprocess ... | Unknown | Unknown |  |
| jarvis_memory/chroma.sqlite3 |  |  | Unknown | Unknown |  |
| main.py | Primary entrypoint; initializes JarvisAssistant and runs loops/services. | asyncio, automation.browser_state_tracker, automation.services, awareness.controller, awareness.system_monitor, awareness.windows_accessibility, capabilities, collections ... | Unknown | Unknown |  |
| memory.index |  |  | Unknown | Unknown |  |
| memory.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| memory/__init__.py | Memory subsystem utilities for Jarvis. | memory_controller, short_term_buffer | Unknown | Unknown |  |
| memory/memory_controller.py | High-level memory controller orchestrating short- and long-term storage. | __future__, dataclasses, datetime, memory_core, re, short_term_buffer, typing, vector_memory | Unknown | Unknown |  |
| memory/short_term_buffer.py | Short-term conversational memory buffer. | collections, dataclasses, typing | Unknown | Unknown |  |
| memory/taskbar_anchors.json | Memory subsystem file. |  | Unknown | Low-Medium |  |
| memory/taskbar_chrome_template.png | Memory subsystem file. |  | Unknown | Unknown |  |
| memory/ui_memory.json | Memory subsystem file. |  | Unknown | Low-Medium |  |
| memory_core.py |  | difflib, json, os | Unknown | Unknown |  |
| memory_store/metadata.npy |  |  | Unknown | Unknown |  |
| memory_store/vector.index |  |  | Unknown | Unknown |  |
| mobile_dashboard/package.json | React/Vite mobile dashboard file. |  | Unknown | Medium |  |
| mobile_dashboard/src/App.jsx | React/Vite mobile dashboard file. |  | Unknown | Medium |  |
| mobile_dashboard/src/main.jsx | React/Vite mobile dashboard file. |  | Unknown | Medium |  |
| mobile_dashboard/src/styles.css | React/Vite mobile dashboard file. |  | Unknown | Medium |  |
| mobile_dashboard/vite.config.js | React/Vite mobile dashboard file. |  | Unknown | Medium |  |
| New Text Document.txt |  |  | Unknown | Unknown |  |
| ocr_roi_test.py |  | PIL, cv2, numpy, pytesseract | Experimental | Unknown |  |
| ocr_test.py |  | PIL, pytesseract | Experimental | Unknown |  |
| package-lock.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| package.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| personality.py | Defines the personality and response style of JARVIS. |  | Unknown | Unknown |  |
| playwright.config.ts |  |  | Unknown | Unknown |  |
| plugins/__init__.py | Plugin package enabling modular Jarvis capabilities. | loader | Unknown | Unknown |  |
| plugins/calendar_scheduler/manifest.json | Plugin system file. |  | Unknown | Low-Medium |  |
| plugins/calendar_scheduler/module.py | Calendar scheduling plugin leveraging automation services. | __future__, automation.services, core.capability_dispatcher, datetime, typing | Unknown | Unknown |  |
| plugins/gmail_sender/manifest.json | Plugin system file. |  | Unknown | Low-Medium |  |
| plugins/gmail_sender/module.py | Gmail email sending plugin using Playwright automation. | __future__, automation.gmail_actions, core.capability_dispatcher, core.intent_parser | Unknown | Unknown |  |
| plugins/loader.py | Plugin loading infrastructure for Jarvis. | __future__, capabilities, core.capability_dispatcher, dataclasses, importlib.util, json, pathlib, sys ... | Unknown | Unknown |  |
| plugins/status_monitor/manifest.json | Plugin system file. |  | Unknown | Low-Medium |  |
| plugins/status_monitor/module.py | Sample status monitor plugin. | __future__, awareness.system_monitor, core.capability_dispatcher, typing | Unknown | Unknown |  |
| project_intelligence/_test.txt |  |  | Unknown | Unknown |  |
| project_intelligence/CODEBASE_INVENTORY.md | Documentation. |  | Unknown | Low-Medium |  |
| project_intelligence/extract_intelligence.py |  |  | Unknown | Unknown |  |
| project_intelligence/EXTRACTION_RUN.md | Documentation. |  | Unknown | Low-Medium |  |
| project_intelligence/GRAPHIFY_EXPORT/JARVIS_ARCHITECTURE_GRAPH1.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| project_intelligence/GRAPHIFY_EXPORT/JARVIS_DEPENDENCY_GRAPH1.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| project_intelligence/GRAPHIFY_EXPORT/JARVIS_FAILURE_GRAPH1.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| project_intelligence/GRAPHIFY_EXPORT/JARVIS_FEATURE_STATUS_GRAPH1.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| project_intelligence/GRAPHIFY_EXPORT/JARVIS_FRIDAY_PIVOT_GRAPH1.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| project_intelligence/GRAPHIFY_EXPORT/JARVIS_MASTER_INTELLIGENCE_GRAPH1.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| project_intelligence/GRAPHIFY_EXPORT/JARVIS_ROADMAP_GRAPH1.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| project_intelligence/GRAPHIFY_EXPORT/JARVIS_RUNTIME_FLOW_GRAPH1.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| project_intelligence/python_index.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| project_intelligence/repo_index.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| project_intelligence/small.py |  |  | Unknown | Unknown |  |
| pytest.ini | Config file. |  | Unknown | Low-Medium |  |
| quick_test_maps.py |  | dotenv, services.maps_service | Unknown | Unknown |  |
| README.md | Documentation. |  | Working | Low-Medium |  |
| remote/telegram_relay.py |  | asyncio, dotenv, os, pathlib, requests, sys, telegram, telegram.ext ... | Unknown | Medium-High |  |
| remote/webhook_server.py |  | collections, dotenv, fastapi, hashlib, hmac, json, os, pathlib ... | Unknown | Medium-High |  |
| requirements-312.txt |  |  | Unknown | Unknown |  |
| requirements-dev.txt |  |  | Unknown | Unknown |  |
| requirements.txt |  |  | Unknown | Unknown |  |
| roi_change_ocr.py |  | cv2, mss, numpy, pytesseract, time | Unknown | Unknown |  |
| roi_changes_test.py |  | cv2, mss, numpy, time | Experimental | Unknown |  |
| scripts/reality_check.ps1 | PowerShell script / test harness. |  | Unknown | Low-Medium |  |
| scripts/run_mock_and_tests.ps1 | PowerShell script / test harness. |  | Unknown | Low-Medium |  |
| scripts/self_repair_test.ps1 | PowerShell script / test harness. |  | Unknown | Low-Medium |  |
| scripts/setup_dev_env.ps1 | PowerShell script / test harness. |  | Unknown | Low-Medium |  |
| scripts/start_telegram_relay.ps1 | PowerShell script / test harness. |  | Unknown | Low-Medium |  |
| scripts/taskbar_debug_run.py |  | __future__, argparse, automation.taskbar_locator, automation.taskbar_trainer, cv2, json, pathlib, sys ... | Unknown | Low-Medium |  |
| scripts/test_open_chrome.ps1 | PowerShell script / test harness. |  | Unknown | Low-Medium |  |
| security/__init__.py | Security module for credential management and vault operations. | credential_vault | Unknown | High |  |
| security/credential_vault.py | Secure credential vault using Windows DPAPI encryption. | __future__, json, os, pathlib, threading, typing, win32crypt | Unknown | High |  |
| security/credentials.dat | Security/credential handling file. |  | Unknown | High |  |
| server/__init__.py | Remote control server package. |  | Unknown | Medium-High |  |
| server/app.py | FastAPI remote control server for Jarvis. | __future__, collections, fastapi, fastapi.responses, fastapi.staticfiles, ipaddress, json, os ... | Unknown | Medium-High |  |
| server/static/index.html | Remote FastAPI server / dashboard file. |  | Unknown | Medium-High |  |
| services/distancematrix_service.py | External API service helper. | config, dataclasses, os, requests, typing | Unknown | Unknown |  |
| services/maps_service.py | External API service helper. | services.distancematrix_service | Unknown | Unknown |  |
| services/market_service.py | Utility helpers for stock and crypto quotes via Yahoo Finance. | __future__, config, datetime, requests, typing | Unknown | Unknown |  |
| services/news_service.py | Lightweight client for fetching news headlines via GNews API. | __future__, config, requests, typing | Unknown | Unknown |  |
| services/search_service.py | Simple web search abstraction using DuckDuckGo Instant Answer API. | __future__, config, requests | Unknown | Unknown |  |
| services/weather_service.py | External API service helper. | config, os, requests, time, typing | Unknown | Unknown |  |
| start_remote_server.py |  | queue, server.app, time | Unknown | Unknown |  |
| test.png |  |  | Unknown | Unknown |  |
| test_pydantic_ai.py | Simple PydanticAI verification script. | dotenv, os, pydantic_ai | Unknown | Unknown |  |
| test_runtime_fixes.ps1 | PowerShell script / test harness. |  | Unknown | Unknown |  |
| tests/__init__.py |  |  | Experimental | Low-Medium |  |
| tests/mocks/mock_api.py |  | __future__, flask, math, typing | Experimental | Low-Medium |  |
| tests/test_automation_components.py |  | __future__, asyncio, automation, automation.browser_state_tracker, awareness.event_dispatcher, awareness.types, pytest, typing | Experimental | Low-Medium |  |
| tests/test_awareness.py |  | __future__, awareness.event_dispatcher, awareness.state_cache, awareness.types, collections, pytest, typing | Experimental | Low-Medium |  |
| tests/test_awareness_state_cache.py |  | asyncio, automation.browser_state_tracker, types | Experimental | Low-Medium |  |
| tests/test_capabilities.py |  | capabilities, core.assistant, core.capability_dispatcher, memory.memory_controller, personality | Experimental | Low-Medium |  |
| tests/test_capability_priority_edge_cases.py |  | capabilities | Experimental | Low-Medium |  |
| tests/test_distancematrix.py |  | json, services.distancematrix_service, types | Experimental | Low-Medium |  |
| tests/test_maps_distance.py |  | os, pytest, re, services.maps_service | Experimental | Low-Medium |  |
| tests/test_planner.py |  | __future__, automation.planner, dataclasses, pytest | Experimental | Low-Medium |  |
| tests/test_planner_recovery.py |  | automation.planner, automation.services, types | Experimental | Low-Medium |  |
| tests/test_planner_reload.py |  | automation.planner, automation.services | Experimental | Low-Medium |  |
| tests/test_prompt_builder.py |  | capabilities, core.assistant, core.capability_dispatcher, memory.memory_controller, personality, re | Experimental | Low-Medium |  |
| tests/test_remote_execute.py |  | fastapi.testclient, importlib | Experimental | Low-Medium |  |
| tests/test_remote_reload.py |  | fastapi.testclient, importlib | Experimental | Low-Medium |  |
| tests/test_state_cache_ocr.py |  | awareness.state_cache, time | Experimental | Low-Medium |  |
| tests/test_taskbar_utils.py |  | __future__, automation.taskbar_trainer | Experimental | Low-Medium |  |
| tests/test_webhook_hmac.py |  | fastapi.testclient, hashlib, hmac, importlib, json, os | Experimental | Low-Medium |  |
| testsprite_tests/.gitkeep |  |  | Unknown | Unknown |  |
| testsprite_tests/standard_prd.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| testsprite_tests/testsprite_backend_test_plan.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| testsprite_tests/tmp/code_summary.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| testsprite_tests/tmp/config.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| testsprite_tests/tmp/prd_files/.gitkeep |  |  | Unknown | Unknown |  |
| testsprite_tests/tmp/prd_files/README.md | Documentation. |  | Working | Low-Medium |  |
| tts_formatter.py |  | personality, re, urllib.parse | Unknown | Unknown |  |
| ui/__init__.py | User interface components and IPC bridges. |  | Unknown | Unknown |  |
| ui/ipc_server.py | WebSocket-based IPC bridge between Jarvis core and desktop UI. | __future__, asyncio, dataclasses, json, typing, websockets, websockets.server | Unknown | Unknown |  |
| ui/web_client/index.html | UI / IPC client/server file. |  | Unknown | Unknown |  |
| ui_patterns.json | Configuration/data JSON. |  | Unknown | Low-Medium |  |
| vector_memory.py |  | datetime, faiss, json, math, numpy, os, sentence_transformers, typing | Unknown | Unknown |  |
| voice_io.py |  | speech_recognition | Unknown | Unknown |  |
| wake_word_listener.py |  | os, pvporcupine, pyaudio, struct | Unknown | Unknown |  |
| wake_words/jarvis_en_windows.ppn |  |  | Unknown | Unknown |  |
| wake_words/listen_en_windows.ppn |  |  | Unknown | Unknown |  |
| win_action_test.py |  | ctypes, time | Experimental | Unknown |  |
