"""Captcha solver — attempt to solve captchas the WebAgent encounters.

Strategy (in priority order, cheapest/fastest first):

1. **Stealth avoidance** — the browser controller patches navigator.webdriver and
   connects via CDP to the user's real Chrome (which carries real cookies and
   browsing history). Most captchas never trigger because the session looks human.

2. **NopeCHA extension** — if the user has the NopeCHA Chrome extension installed
   (free for personal use), it auto-solves reCAPTCHA/hCaptcha in the background.
   We just wait for it to do its thing.

3. **NopeCHA API** — if the extension isn't installed but a NOPECHA_KEY is in .env,
   call the NopeCHA API to solve the captcha programmatically.

4. **Honest stop** — if nothing works, report the captcha honestly and let the
   user intervene (solve it manually, then FRIDAY continues).

This module is called by the WebAgent when it detects a captcha/verification wall.
It does NOT brute-force or bypass security — it uses legitimate solving services
that the user explicitly configures.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional


def attempt_captcha_solve(browser_controller: Any, timeout: float = 30.0) -> bool:
    """Attempt to solve a captcha on the current page.

    Returns True if the captcha was solved (page moved past it), False otherwise.
    Never raises — captcha solving is best-effort.
    """
    if not browser_controller or not getattr(browser_controller, "available", False):
        return False

    # Strategy 1: Wait for NopeCHA extension to auto-solve (if installed)
    # The extension auto-detects and solves captchas. We just need to wait.
    solved = _wait_for_extension_solve(browser_controller, timeout=min(timeout, 15.0))
    if solved:
        return True

    # Strategy 2: Use NopeCHA Python API
    api_key = os.environ.get("NOPECHA_KEY", "").strip()
    if api_key:
        solved = _solve_via_api(browser_controller, api_key, timeout=timeout)
        if solved:
            return True

    return False


def _wait_for_extension_solve(browser_controller: Any, timeout: float = 15.0) -> bool:
    """Wait for a browser extension (NopeCHA/Buster) to solve the captcha.

    Checks every second whether the page URL has changed (indicating the captcha
    was solved and the site moved forward).
    """
    try:
        initial_url = browser_controller.current_url()
        deadline = time.monotonic() + timeout
        step = 1.0

        while time.monotonic() < deadline:
            time.sleep(step)
            current = browser_controller.current_url()
            if current != initial_url and "captcha" not in current.lower() and "recaptcha" not in current.lower():
                return True
            # Also check if the captcha iframe disappeared
            page_text = browser_controller.read_text(500) if hasattr(browser_controller, "read_text") else ""
            if page_text and "captcha" not in page_text.lower() and "verify" not in page_text.lower():
                return True
    except Exception:
        pass
    return False


def _solve_via_api(browser_controller: Any, api_key: str, timeout: float = 30.0) -> bool:
    """Use the NopeCHA Python API to solve a reCAPTCHA on the current page.

    This requires the `nopecha` package and a valid API key.
    """
    try:
        import nopecha
        nopecha.api_key = api_key

        # Get the site key from the reCAPTCHA iframe on the page
        site_key = browser_controller._submit(browser_controller._page.evaluate("""() => {
            const iframe = document.querySelector('iframe[src*="recaptcha"]');
            if (!iframe) return null;
            const src = iframe.src;
            const match = src.match(/[?&]k=([^&]+)/);
            return match ? match[1] : null;
        }"""))

        if not site_key:
            return False

        url = browser_controller.current_url()

        # Solve via NopeCHA API
        token = nopecha.Token.solve(
            type="recaptcha2",
            sitekey=site_key,
            url=url,
        )

        if not token:
            return False

        # Inject the solution token into the page
        browser_controller._submit(browser_controller._page.evaluate(f"""(token) => {{
            const textarea = document.querySelector('#g-recaptcha-response');
            if (textarea) {{
                textarea.value = token;
                textarea.style.display = 'block';
            }}
            // Also try callback
            if (typeof ___grecaptcha_cfg !== 'undefined') {{
                const clients = ___grecaptcha_cfg.clients;
                if (clients) {{
                    Object.keys(clients).forEach(key => {{
                        const client = clients[key];
                        if (client && client.callback) {{
                            client.callback(token);
                        }}
                    }});
                }}
            }}
        }}""", token))

        # Wait for the page to react
        time.sleep(3.0)
        current = browser_controller.current_url()
        return "captcha" not in current.lower() and "recaptcha" not in current.lower()

    except ImportError:
        return False
    except Exception:
        return False
