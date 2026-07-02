# FRIDAY Desktop (Tauri)

Native desktop shell for FRIDAY. React frontend + Rust (Tauri) backend
that launches the Python FRIDAY API as a sidecar.

## Development (no Rust needed — browser mode)

```bash
cd desktop_tauri
npm install
npm run dev        # Opens at http://localhost:3000
```

Start the backend separately:
```bash
python -m friday.api.server
```

The UI connects to the API at localhost:8801. Enter your REMOTE_API_KEY
on first launch.

## Full Desktop App (requires Rust)

Prerequisites:
- Rust toolchain (https://rustup.rs)
- MSVC C++ Build Tools
- WebView2 (pre-installed on Windows 11)

```bash
cd desktop_tauri
npm install
npm run tauri dev      # Native window with hot reload
npm run tauri build    # Produces installer in src-tauri/target/release/bundle/
```

## Architecture

```
┌─────────────────────────────┐
│   Tauri Window (native)      │
│   ┌───────────────────────┐  │
│   │  React UI (src/)       │  │
│   │  - Chat interface      │  │
│   │  - Status panel        │  │
│   │  - JARVIS/FRIDAY mode  │  │
│   └──────────┬────────────┘  │
│              │ HTTP/WS        │
│   ┌──────────▼────────────┐  │
│   │  Rust backend          │  │
│   │  (src-tauri/)          │  │
│   │  - Launches sidecar    │  │
│   │  - System tray         │  │
│   └──────────┬────────────┘  │
└──────────────┼───────────────┘
               │ spawns
        ┌──────▼──────────┐
        │ Python FRIDAY   │
        │ API (port 8801) │
        │ NVIDIA + memory │
        └─────────────────┘
```

## Files
- `src/App.tsx` — Main UI
- `src/api.ts` — API client (shared contract with mobile)
- `src/styles.css` — Dark theme
- `src-tauri/src/main.rs` — Rust backend (sidecar + tray)
- `src-tauri/Cargo.toml` — Rust dependencies
- `src-tauri/tauri.conf.json` — Tauri config
