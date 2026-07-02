# FRIDAY Backend Packaging

Builds a distributable FRIDAY backend executable so friends can run it
without installing Python.

Per ADR-017, this packages the **backend platform only** (API + cognitive
engine). The UI is a separate future deliverable.

## Build

```powershell
pip install pyinstaller
pyinstaller packaging/friday_backend.spec
```

Output: `dist/friday-backend/friday-backend.exe`

## What Gets Bundled
- FRIDAY API server (FastAPI + uvicorn)
- Full cognitive platform (perception, planning, memory, verification)
- Model router (NVIDIA + Groq providers)
- All Python dependencies

## What Does NOT Get Bundled (intentional)
- The real `.env` (only `.env.example` template)
- Heavy ML libs (torch, tensorflow, sentence-transformers) — excluded
- Tesseract binary (OCR) — system dependency, optional
- UI (deferred per ADR-017)

## First-Run Setup for Friends

1. Run `friday-backend.exe`
2. On first launch, it creates a `.env` from the template (or prompts)
3. User adds their `NVIDIA_API_KEY` and sets `REMOTE_API_KEY`
4. API serves at `http://127.0.0.1:8801`
5. Docs at `http://127.0.0.1:8801/docs`

## Configuration Wizard

`packaging/first_run.py` provides an interactive setup that:
- Validates Python deps (when run from source)
- Creates `.env` from template
- Prompts for required API keys
- Tests NVIDIA/Groq connectivity
- Verifies the server starts

## Distribution

Zip `dist/friday-backend/` and share. Recipients extract and run the .exe.
No Python install needed. For a true installer (NSIS/MSI), that comes with
the desktop app phase (deferred).

## Notes
- Build requires the same OS/arch as the target (Windows x64)
- First build is slow (~minutes); subsequent builds faster
- UPX compression reduces size (~50-100MB final)
