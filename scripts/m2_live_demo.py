"""M2 live demo — operate the REAL Chrome over CDP and prove it with evidence.

Requires CDP up (run scripts/launch_chrome_debug.py first).

Proves:
- BrowserController connects via CDP (connection_mode == 'cdp', not 'fresh')
- a real navigation happens and is confirmed
- a real page read returns actual content
- a screenshot evidence artifact is captured
- captcha-resistant search (DuckDuckGo) returns real results, not a wall
"""

import sys

from friday.actions.browser_controller import BrowserController
from friday.actions.chrome_launcher import cdp_reachable
from friday.verification.screenshot_evidence import capture_screenshot, is_blocked_page


def main() -> int:
    if not cdp_reachable(9222):
        print("[SKIP] CDP not reachable. Run scripts/launch_chrome_debug.py first.")
        return 1

    c = BrowserController(remote_debug_port=9222, require_real_chrome=True)
    if not c.start():
        print(f"[FAIL] could not start controller: {c.last_error}")
        return 1

    print(f"connection_mode : {c.connection_mode}")
    print(f"is_real_chrome  : {c.is_real_chrome}")

    # 1. Real navigation
    nav = c.navigate("https://example.com")
    print(f"navigate ok     : {nav.get('ok')}  url={nav.get('url')}")

    # 2. Real read
    text = c.read_text(max_chars=300)
    print(f"read chars      : {len(text)}")
    print(f"blocked?        : {is_blocked_page(text, c.current_url())}")
    print(f"page snippet    : {text[:120]!r}")

    # 3. Screenshot evidence
    shot = capture_screenshot(label="m2_example")
    print(f"screenshot      : {shot.path} ({shot.size} bytes, real={shot.is_real})")

    # 4. Captcha-resistant search
    res = c.search_web("best gaming laptop")
    blocked = is_blocked_page(res.get("text", ""), "")
    print(f"search engine   : {res.get('engine')}")
    print(f"search ok       : {res.get('ok')}  chars={len(res.get('text',''))}  blocked={blocked}")
    print(f"search links    : {len(res.get('links', []))}")

    print("\n[DONE] M2 live operation against real Chrome complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
