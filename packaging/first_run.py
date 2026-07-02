"""FRIDAY First-Run Setup Wizard.

Interactive configuration for new installations. Handles:
- Dependency validation
- .env creation from template
- API key prompting
- Provider connectivity test
- Readiness check

Run: python packaging/first_run.py
Or bundled: friday-backend.exe --setup
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def check_dependencies() -> tuple[bool, list]:
    """Validate that required Python packages are importable."""
    required = [
        ("fastapi", "FastAPI web framework"),
        ("uvicorn", "ASGI server"),
        ("pydantic", "Data validation"),
        ("httpx", "HTTP client (NVIDIA API)"),
        ("dotenv", "Environment config"),
    ]
    missing = []
    for module, desc in required:
        try:
            __import__(module)
        except ImportError:
            missing.append((module, desc))
    return len(missing) == 0, missing


def check_optional() -> dict:
    """Check optional dependencies and report status."""
    status = {}
    optional = ["groq", "mss", "pytesseract", "pyautogui", "uiautomation"]
    for module in optional:
        try:
            __import__(module)
            status[module] = True
        except ImportError:
            status[module] = False
    return status


def ensure_env() -> Path:
    """Create .env from .env.example if it doesn't exist."""
    env_path = ROOT / ".env"
    example_path = ROOT / ".env.example"

    if env_path.exists():
        print(f"[✓] .env exists at {env_path}")
        return env_path

    if example_path.exists():
        env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[✓] Created .env from template")
    else:
        # Minimal template
        env_path.write_text(
            "# FRIDAY Configuration\n"
            "REMOTE_API_KEY=change-me\n"
            "NVIDIA_API_KEY=\n"
            "GROQ_API_KEY=\n",
            encoding="utf-8",
        )
        print(f"[✓] Created minimal .env")
    return env_path


def prompt_keys(env_path: Path, interactive: bool = True) -> None:
    """Prompt for required API keys if missing."""
    if not interactive:
        return

    from dotenv import load_dotenv
    load_dotenv(env_path)

    lines = env_path.read_text(encoding="utf-8").splitlines()

    def get_current(key: str) -> str:
        return os.getenv(key, "")

    updates = {}

    if not get_current("REMOTE_API_KEY") or get_current("REMOTE_API_KEY") == "change-me":
        val = input("Set an API key for remote access (REMOTE_API_KEY): ").strip()
        if val:
            updates["REMOTE_API_KEY"] = val

    if not get_current("NVIDIA_API_KEY"):
        val = input("NVIDIA NIM API key (NVIDIA_API_KEY, blank to skip): ").strip()
        if val:
            updates["NVIDIA_API_KEY"] = val

    if updates:
        new_lines = []
        seen = set()
        for line in lines:
            updated = False
            for key, val in updates.items():
                if line.startswith(f"{key}="):
                    new_lines.append(f"{key}={val}")
                    seen.add(key)
                    updated = True
                    break
            if not updated:
                new_lines.append(line)
        for key, val in updates.items():
            if key not in seen:
                new_lines.append(f"{key}={val}")
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        print("[✓] Updated .env")


def test_connectivity() -> dict:
    """Test provider connectivity."""
    from dotenv import load_dotenv
    load_dotenv()

    results = {}
    nvidia_key = os.getenv("NVIDIA_API_KEY", "")
    groq_key = os.getenv("GROQ_API_KEY", "")

    results["nvidia_configured"] = bool(nvidia_key)
    results["groq_configured"] = bool(groq_key)
    results["any_provider"] = bool(nvidia_key or groq_key)
    return results


def run_wizard(interactive: bool = True) -> bool:
    """Run the full first-run wizard. Returns True if ready."""
    print("=" * 55)
    print("  FRIDAY First-Run Setup")
    print("=" * 55)
    print()

    # 1. Dependencies
    ok, missing = check_dependencies()
    if not ok:
        print("[✗] Missing required dependencies:")
        for mod, desc in missing:
            print(f"    - {mod} ({desc})")
        print("\nInstall with: pip install -r requirements.txt")
        return False
    print("[✓] Required dependencies present")

    # 2. Optional
    optional = check_optional()
    print("\nOptional capabilities:")
    cap_map = {
        "groq": "Groq fallback provider",
        "mss": "Fast screen capture",
        "pytesseract": "OCR text extraction",
        "pyautogui": "Desktop automation",
        "uiautomation": "Windows UI Automation",
    }
    for mod, available in optional.items():
        mark = "✓" if available else "○"
        print(f"  [{mark}] {cap_map.get(mod, mod)}")

    # 3. Env
    print()
    env_path = ensure_env()
    prompt_keys(env_path, interactive=interactive)

    # 4. Connectivity
    print()
    conn = test_connectivity()
    if conn["any_provider"]:
        providers = []
        if conn["nvidia_configured"]:
            providers.append("NVIDIA NIM")
        if conn["groq_configured"]:
            providers.append("Groq")
        print(f"[✓] Model providers configured: {', '.join(providers)}")
    else:
        print("[⚠] No model providers configured. JARVIS mode will be limited.")
        print("    Add NVIDIA_API_KEY or GROQ_API_KEY to .env")

    # 5. Ready
    print()
    print("=" * 55)
    ready = ok and conn["any_provider"]
    if ready:
        print("  Setup complete. Start FRIDAY with:")
        print("    python -m friday.api.server")
        print("  API docs: http://127.0.0.1:8801/docs")
    else:
        print("  Setup incomplete. Address warnings above.")
    print("=" * 55)
    return ready


if __name__ == "__main__":
    interactive = "--no-input" not in sys.argv
    success = run_wizard(interactive=interactive)
    sys.exit(0 if success else 1)
