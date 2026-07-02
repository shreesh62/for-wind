# Blockers

## Active Blockers

### Disk Space for Rust/Tauri (HIGH)
- **Free: 1.33 GB** — need 5 GB+ for Rust toolchain + Tauri build
- Rust install failed with "not enough space (os error 112)"
- Cleaned up broken partial install (reclaimed ~0.8 GB)
- **Owner action**: free 5 GB, then re-run rustup (see OWNER_ACTION_REQUIRED.md)
- **Impact**: Blocks Phase 10 (Tauri build) + Phase 11 (installer)
- **Workaround**: Desktop frontend runs in browser via `npm run dev` without Rust

## Resolved Blockers

### ~~Owner Approval~~ — 2026-06-08
### ~~Missing Dependencies~~ — 2026-06-08 (pywin32, opencv, mss, httpx)
### ~~Disk Space (round 1)~~ — 2026-06-08 (owner freed 6.6 GB; since consumed)
### ~~FastAPI/Starlette Incompatibility~~ — 2026-06-09 (upgraded to 0.136.3)

## Notes (Non-Blocking)
- NVIDIA NIM: cold ~29s, warm ~2.4s. JARVIS caps tokens at 512.
- Tesseract OCR optional (4 other perception sources work without it)
