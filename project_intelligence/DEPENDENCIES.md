# Dependencies (Python, Node, System)

This document enumerates declared dependencies and "implicit" dependencies discovered in code.

Confidence: High for declared deps; Medium for implicit deps (environment may already include them).

## Python Dependencies (Declared)

Declared in `requirements.txt`:
- `python-dotenv==1.0.1`
- `requests==2.32.5`
- `fastapi==0.115.2`
- `uvicorn==0.30.6`
- `pydantic==2.12.4`
- `websockets==12.0`
- `playwright==1.55.0`
- `edge-tts==7.2.3`
- `playsound==1.2.2`
- `pvporcupine==3.0.5`
- `PyAudio==0.2.14`
- `pyttsx3==2.99`
- `SpeechRecognition==3.10.4`
- `groq==0.33.0`
- `numpy==2.1.3`
- `faiss-cpu==1.13.1; platform_system != "Windows"`
- `sentence-transformers==2.7.0; platform_system != "Windows"`
- `psutil==5.9.8`
- `pyautogui==0.9.54`
- `pywinauto==0.6.8`
- `pillow==10.4.0`
- `uiautomation==2.0.18`
- `pytesseract==0.3.10`

Dev/test deps in `requirements-dev.txt`:
- `pytest==8.3.4`
- `flask==3.0.3` (note: Flask appears unused for core runtime; likely experimental)
- `httpx==0.25.2`
- `python-telegram-bot==20.6`

Python 3.12 snapshot in `requirements-312.txt` duplicates the above pins.

## Node/JS Dependencies (Declared)

Root `package.json` (test tooling):
- `@playwright/test`
- `@types/node`

`desktop_app/package.json` (Electron shell):
- runtime: `electron`
- dev: `electron-builder`, `eslint`, `cross-env`

`mobile_dashboard/package.json` (React/Vite):
- runtime: `react`, `react-dom`
- dev: `vite`, `@vitejs/plugin-react`

## Implicit / Missing / Not-Pinned Dependencies (High Risk)

These are imported in code but NOT pinned in `requirements*.txt`:

1. `pywin32` (Windows DPAPI)
   - Evidence: `security/credential_vault.py` imports `win32crypt`.
   - Without `pywin32`, credential vault is unavailable and will raise.

2. OpenCV (`cv2`) and likely `opencv-python`
   - Evidence: `automation/chrome_pipeline.py`, `automation/taskbar_trainer.py`, `automation/taskbar_locator.py`, `roi_change_ocr.py` import `cv2`.
   - Without this package, taskbar anchoring and visual matching will fail.

3. `mss`
   - Evidence: `roi_change_ocr.py` imports `mss`.
   - Used only by experimental ROI change detection scripts.

4. `torch` + `clip`
   - Evidence: `clip_test.py` imports `clip`, `torch`.
   - Experimental only.

5. `pydantic_ai`
   - Evidence: `test_pydantic_ai.py` imports `pydantic_ai.Agent`.
   - Experimental only.

Recommendation:
- Either pin these (and mark optional extras) or clearly document them as experimental-only.

## System/External Dependencies (Non-Python)

1. Chrome / Chromium
   - Browser automation relies on Playwright AND on attaching to a real Chrome via DevTools.
   - README mentions launching Chrome with `--remote-debugging-port=9222` for browser summaries.

2. Tesseract OCR binary
   - `pytesseract` typically requires Tesseract installed and accessible in PATH or configured.
   - Without Tesseract, OCR features will be broken even if Python packages are installed.

3. Audio I/O
   - Wake word requires microphone access and a working audio stack for PyAudio.

4. Windows-only APIs
   - UI automation and DPAPI are Windows-centric; portability is not a goal.

## Dependency Graphs

Graphify exports:
- `project_intelligence/GRAPHIFY_EXPORT/JARVIS_DEPENDENCY_GRAPH1.json`

