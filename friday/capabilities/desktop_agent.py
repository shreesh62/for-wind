"""Desktop Agent — vision-first, human-like computer control.

Like OpenClaw / OpenManus: take a screenshot, send it to the VLM, let the model
SEE the screen and decide what to do. No DOM parsing, no element lists, no CDP.
Just: screenshot → VLM reasoning → pyautogui action → repeat.

This is what makes FRIDAY a real desktop agent:
- Takes a screenshot of the ACTUAL screen
- Sends it to the vision model (llama-3.2-90b-vision)
- The model sees exactly what a human sees and decides the next action
- Executes via pyautogui (mouse click at coordinates, keyboard typing)
- Takes another screenshot to see what happened
- Repeats until the goal is achieved

No site-specific code. No automation detection. Works on ANY application.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pyautogui

# Safety: don't let pyautogui move too fast
pyautogui.PAUSE = 0.3


SYSTEM_PROMPT = """You are a computer-use agent. You can see the screen and control the mouse and keyboard.

You will receive a screenshot of the current screen state. Based on what you SEE, decide the single next action to take toward the goal.

Available actions (respond with JSON only):
{"action": "click", "x": 500, "y": 300, "why": "clicking the login button"}
{"action": "double_click", "x": 500, "y": 300, "why": "opening a file"}
{"action": "type", "text": "hello world", "why": "typing into the focused field"}
{"action": "hotkey", "keys": ["ctrl", "l"], "why": "focusing the address bar"}
{"action": "press", "key": "enter", "why": "submitting the form"}
{"action": "scroll", "direction": "down", "amount": 3, "why": "scrolling to see more"}
{"action": "wait", "seconds": 2, "why": "waiting for page to load"}
{"action": "login", "username_x": 500, "username_y": 200, "password_x": 500, "password_y": 260, "submit_x": 500, "submit_y": 320, "why": "filling login form"}
{"action": "done", "why": "goal achieved because I can see..."}
{"action": "stuck", "why": "cannot proceed because..."}

Rules:
- Look at the screenshot carefully. Describe what you see BEFORE choosing an action.
- Click coordinates are ABSOLUTE screen pixels from the screenshot.
- If you need to type into a field, CLICK it first to focus it, THEN type in the next step.
- After clicking a button, wait a moment for the page to respond before acting again.
- If you see you're already logged in (a feed/home page with posts/stories), and the goal includes "log in if needed", skip login and proceed with the rest of the goal.
- If you see a LOGIN FORM (username/password fields + submit button), use the "login" action with the coordinates of the username field, password field, and submit button. The system will handle credential entry securely without you seeing the passwords.
- If you see a captcha, click on it to try solving it.
- Use "done" when you can SEE evidence the goal is complete on screen.
- Be precise with coordinates — click the CENTER of buttons/fields.
- Minimize steps. Don't scroll unnecessarily. Act decisively.
"""


@dataclass
class DesktopAgentResult:
    """Outcome of the desktop agent's goal attempt."""
    goal: str
    achieved: bool = False
    steps_taken: int = 0
    history: List[str] = field(default_factory=list)
    stuck_reason: str = ""
    screenshots: List[str] = field(default_factory=list)


def _extract_credentials(goal: str) -> Dict[str, str]:
    """Extract username/password from the goal text. Never sent to the VLM."""
    import re
    creds = {}
    # Username patterns
    for pattern in [
        r"username[:\s]+([^\s,]+)",
        r"user(?:name)?[:\s]+([^\s,]+)",
        r"email[:\s]+([^\s,]+)",
    ]:
        m = re.search(pattern, goal, re.IGNORECASE)
        if m:
            creds["username"] = m.group(1).strip("\"'")
            break
    # Password patterns
    for pattern in [
        r"password[:\s]+([^\s,\.]+)",
        r"pass(?:word)?[:\s]+([^\s,\.]+)",
    ]:
        m = re.search(pattern, goal, re.IGNORECASE)
        if m:
            creds["password"] = m.group(1).strip("\"'")
            break
    return creds


def _sanitize_goal_for_vlm(goal: str, creds: Dict[str, str]) -> str:
    """Remove credentials from the goal before sending to the VLM.
    
    The VLM sees the goal without passwords — it only needs to know WHERE to
    click, not WHAT to type. Credentials are handled by the secure login action.
    Also removes login-related language that triggers content safety filters on
    some models — the VLM just needs to know "if you see a login form, use the
    login action."
    """
    sanitized = goal
    if creds.get("password"):
        sanitized = sanitized.replace(creds["password"], "")
    if creds.get("username"):
        sanitized = sanitized.replace(creds["username"], "")
    # Remove credential patterns entirely
    import re
    sanitized = re.sub(r"(?i)(username|user|email)[:\s]+\S+", "", sanitized)
    sanitized = re.sub(r"(?i)(password|pass)[:\s]+\S+", "", sanitized)
    sanitized = re.sub(r"\[PASSWORD\]|\[USERNAME\]", "", sanitized)
    # Clean up extra whitespace
    sanitized = re.sub(r"\s{2,}", " ", sanitized).strip()
    return sanitized


class DesktopAgent:
    """Vision-first desktop agent. Screenshot → VLM → action → repeat."""

    def __init__(self, model_router, *, max_steps: int = 20) -> None:
        self._router = model_router
        self._max_steps = max_steps

    def run(self, goal: str) -> DesktopAgentResult:
        """Run the agent toward a goal by observing the screen and acting."""
        result = DesktopAgentResult(goal=goal)

        if not self._router:
            result.stuck_reason = "no model router"
            return result

        # Extract credentials BEFORE sending anything to the VLM
        creds = _extract_credentials(goal)
        safe_goal = _sanitize_goal_for_vlm(goal, creds)

        last_action = "(none yet — this is the first step)"

        for step in range(self._max_steps):
            # Re-focus the target window before each screenshot
            self._refocus_target()
            time.sleep(0.3)

            # 1. SCREENSHOT — see what's on screen right now
            screenshot = pyautogui.screenshot()
            
            # Save for evidence
            import tempfile, os
            shot_dir = os.path.join(os.path.expanduser("~"), ".friday", "agent_screenshots")
            os.makedirs(shot_dir, exist_ok=True)
            shot_path = os.path.join(shot_dir, f"step_{step:02d}.png")
            screenshot.save(shot_path)
            result.screenshots.append(shot_path)

            # 2. DECIDE — send screenshot to VLM (with sanitized goal, no creds)
            decision = self._decide(safe_goal, screenshot, last_action, step, result.history)
            action = decision.get("action", "stuck")
            why = decision.get("why", "")

            result.history.append(f"step {step+1}: {action} — {why[:80]}")
            print(f"  [{step+1}/{self._max_steps}] {action}: {why[:60]}")

            # 3. ACT
            if action == "done":
                result.achieved = True
                break
            elif action == "stuck":
                result.stuck_reason = why
                break
            elif action == "login":
                # SECURE LOGIN: type credentials directly without the VLM seeing them
                self._execute_login(decision, creds)
                time.sleep(2.0)
                last_action = "filled login form and submitted (credentials handled securely)"
            elif action == "click":
                x, y = int(decision.get("x", 0)), int(decision.get("y", 0))
                pyautogui.click(x, y)
                time.sleep(0.5)
                last_action = f"clicked at ({x}, {y}): {why}"
            elif action == "double_click":
                x, y = int(decision.get("x", 0)), int(decision.get("y", 0))
                pyautogui.doubleClick(x, y)
                time.sleep(0.5)
                last_action = f"double-clicked at ({x}, {y}): {why}"
            elif action == "type":
                text = decision.get("text", "")
                pyautogui.typewrite(text, interval=0.03)
                time.sleep(0.3)
                last_action = f"typed '{text[:30]}'"
            elif action == "hotkey":
                keys = decision.get("keys", [])
                if keys:
                    pyautogui.hotkey(*keys)
                    time.sleep(0.3)
                last_action = f"pressed hotkey {'+'.join(keys)}"
            elif action == "press":
                key = decision.get("key", "enter")
                pyautogui.press(key)
                time.sleep(0.3)
                last_action = f"pressed {key}"
            elif action == "scroll":
                direction = decision.get("direction", "down")
                amount = int(decision.get("amount", 3))
                clicks = -amount if direction == "down" else amount
                pyautogui.scroll(clicks)
                time.sleep(0.5)
                last_action = f"scrolled {direction} by {amount}"
            elif action == "wait":
                seconds = min(float(decision.get("seconds", 2)), 5.0)
                time.sleep(seconds)
                last_action = f"waited {seconds}s"
            else:
                last_action = f"unknown action: {action}"

            result.steps_taken = step + 1

        return result

    def _execute_login(self, decision: Dict[str, Any], creds: Dict[str, str]) -> None:
        """Execute a login form fill securely — no credentials sent to the VLM.

        The VLM provided coordinates for the username field, password field, and
        submit button. We click each and type the credentials directly via pyautogui.
        Fast subroutine: ~2s total for the whole login sequence.
        """
        username = creds.get("username", "")
        password = creds.get("password", "")

        ux = int(decision.get("username_x", 0))
        uy = int(decision.get("username_y", 0))
        px = int(decision.get("password_x", 0))
        py = int(decision.get("password_y", 0))
        sx = int(decision.get("submit_x", 0))
        sy = int(decision.get("submit_y", 0))

        # Click username field → type username
        if ux and uy and username:
            pyautogui.click(ux, uy)
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "a")
            pyautogui.typewrite(username, interval=0.02)
            time.sleep(0.2)

        # Click password field → type password
        if px and py and password:
            pyautogui.click(px, py)
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "a")
            pyautogui.typewrite(password, interval=0.02)
            time.sleep(0.2)

        # Click submit
        if sx and sy:
            pyautogui.click(sx, sy)
        else:
            pyautogui.press("enter")

    def _refocus_target(self) -> None:
        """Bring the target window (Chrome) back to the foreground before screenshots.
        
        Without this, after a click the IDE/terminal might steal focus, and the
        next screenshot shows the wrong window.
        """
        try:
            chrome_wins = pyautogui.getWindowsWithTitle("Chrome")
            if chrome_wins:
                win = chrome_wins[0]
                if not getattr(win, "isActive", False):
                    win.activate()
        except Exception:
            pass

    def _decide(self, goal: str, screenshot, last_action: str, step: int,
                history: List[str]) -> Dict[str, Any]:
        """Send screenshot to VLM and get the next action."""
        import base64
        from io import BytesIO

        # Convert PIL screenshot to base64 for the vision model
        buffer = BytesIO()
        # Resize to reduce token cost (1280 wide is enough for the model to see)
        w, h = screenshot.size
        if w > 1280:
            ratio = 1280 / w
            screenshot = screenshot.resize((1280, int(h * ratio)))
        screenshot.save(buffer, format="PNG")
        img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        image_url = f"data:image/png;base64,{img_b64}"

        recent_history = "\n".join(history[-5:]) if history else "(none)"

        prompt = (
            f"GOAL: {goal}\n\n"
            f"STEP: {step + 1}/{self._max_steps}\n"
            f"LAST ACTION RESULT: {last_action}\n\n"
            f"RECENT HISTORY:\n{recent_history}\n\n"
            "Look at the screenshot above. What do you see? What is the next action?\n"
            "Respond with a single JSON object only."
        )

        try:
            import asyncio
            import concurrent.futures as cf

            with cf.ThreadPoolExecutor(max_workers=1) as pool:
                from friday.models.router import ModelCapability
                fut = pool.submit(asyncio.run, self._router.complete(
                    prompt,
                    capability=ModelCapability.VISION,
                    model="meta/llama-3.2-90b-vision-instruct",
                    max_tokens=300,
                    temperature=0.1,
                    system_prompt=SYSTEM_PROMPT,
                    image_url=image_url,
                ))
                resp = fut.result(timeout=60)

            return self._parse(resp.text)
        except Exception as exc:
            return {"action": "stuck", "why": f"vision model error: {exc}"}

    def _parse(self, text: str) -> Dict[str, Any]:
        """Parse the VLM's JSON response."""
        try:
            # Find JSON in the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start < 0 or end <= start:
                return {"action": "stuck", "why": f"no JSON in response: {text[:100]}"}
            return json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError) as exc:
            return {"action": "stuck", "why": f"invalid JSON: {text[:100]}"}
