"""Chrome open + unlock pipeline using taskbar-anchored visual system.

Replaces all legacy Chrome automation with:
- Visual taskbar icon location
- Profile selection via OCR
- Passive extension lock detection
- State-verified unlock

No coordinates. No process names. Pure visual anchoring.
"""

from __future__ import annotations

import time
from typing import Optional

import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab

from automation.taskbar_locator import click_chrome_icon
from security.credential_vault import get_vault


def wait_for_ocr(text: str, timeout: float = 5.0, poll_interval: float = 0.3) -> bool:
    """Wait for specific text to appear in OCR.
    
    Args:
        text: Text to search for (case-insensitive)
        timeout: Maximum seconds to wait
        poll_interval: Seconds between checks
        
    Returns:
        True if text found, False if timeout
    """
    try:
        import pytesseract
    except ImportError:
        return False
    
    start_time = time.time()
    text_lower = text.lower()
    
    while time.time() - start_time < timeout:
        screenshot = ImageGrab.grab()
        screenshot_np = np.array(screenshot)
        
        # Run OCR
        try:
            ocr_text = pytesseract.image_to_string(screenshot_np).lower()
            
            if text_lower in ocr_text:
                return True
        except Exception:
            pass
        
        time.sleep(poll_interval)
    
    return False


def locate_text_by_ocr(text: str, fuzzy: bool = True) -> Optional[tuple[int, int]]:
    """Locate text on screen using OCR.
    
    Args:
        text: Text to find
        fuzzy: Allow fuzzy matching
        
    Returns:
        (x, y) center coordinates or None
    """
    try:
        import pytesseract
    except ImportError:
        return None
    
    screenshot = ImageGrab.grab()
    screenshot_np = np.array(screenshot)
    
    # Get OCR data with bounding boxes
    try:
        data = pytesseract.image_to_data(screenshot_np, output_type=pytesseract.Output.DICT)
        
        text_lower = text.lower()
        
        for i, word in enumerate(data['text']):
            if not word:
                continue
            
            word_lower = word.lower()
            
            # Exact or fuzzy match
            if fuzzy:
                if text_lower in word_lower or word_lower in text_lower:
                    x = data['left'][i]
                    y = data['top'][i]
                    w = data['width'][i]
                    h = data['height'][i]
                    
                    return (x + w // 2, y + h // 2)
            else:
                if text_lower == word_lower:
                    x = data['left'][i]
                    y = data['top'][i]
                    w = data['width'][i]
                    h = data['height'][i]
                    
                    return (x + w // 2, y + h // 2)
        
    except Exception:
        pass
    
    return None


def handle_profile_selection(profile_name: str = "Shreesh") -> bool:
    """Handle Chrome profile selection screen.
    
    Args:
        profile_name: Profile name to select
        
    Returns:
        True if profile selected, False if failed
    """
    # Wait for profile selection screen
    if not wait_for_ocr("Who's using Chrome", timeout=5.0):
        # Profile screen didn't appear - might already be logged in
        return True
    
    time.sleep(0.5)
    
    # Locate profile by fuzzy OCR match
    coords = locate_text_by_ocr(profile_name, fuzzy=True)
    
    if not coords:
        return False
    
    x, y = coords
    
    # Click with +18px offset (not text itself, but profile button)
    pyautogui.click(x, y + 18)
    
    time.sleep(1.0)
    
    return True


def detect_extension_lock(timeout: float = 5.0) -> bool:
    """Detect if Chrome extension lock screen appeared.
    
    Args:
        timeout: Maximum seconds to wait
        
    Returns:
        True if lock detected
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        screenshot = ImageGrab.grab()
        screenshot_np = np.array(screenshot)
        
        # Check for extension URL in OCR
        try:
            import pytesseract
            ocr_text = pytesseract.image_to_string(screenshot_np).lower()
            
            if "chrome-extension://" in ocr_text:
                return True
        except Exception:
            pass
        
        # Check for text input box (password field)
        gray = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        
        # Look for rectangular input fields
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            
            # Input fields are typically wide and short
            if 100 < w < 600 and 20 < h < 60:
                aspect_ratio = w / h
                if 3 < aspect_ratio < 20:
                    # Likely an input field
                    return True
        
        time.sleep(0.3)
    
    return False


def detect_and_unlock_extension() -> bool:
    """Detect and unlock Chrome extension lock.
    
    Returns:
        True if unlocked successfully, False if failed
    """
    # Wait for lock screen to appear
    if not detect_extension_lock(timeout=5.0):
        # No lock detected - might not be locked
        return True
    
    # Get password from vault
    vault = get_vault()
    
    if not vault.exists("chrome_extension_lock"):
        # Ask user for password once
        import getpass
        print("\nChrome extension lock detected.")
        password = getpass.getpass("Enter Chrome lock password (hidden): ")
        
        if not password:
            raise RuntimeError("Password cannot be empty")
        
        # Save to vault
        vault.set("chrome_extension_lock", password)
        print("Password saved securely.")
    else:
        password = vault.get("chrome_extension_lock")
        
        if not password:
            raise RuntimeError("Chrome extension password is empty")
    
    # Capture before state
    screenshot_before = np.array(ImageGrab.grab())
    before_hash = hash(screenshot_before.tobytes())
    
    # Type password into focused field
    time.sleep(0.3)
    pyautogui.typewrite(password, interval=0.05)
    
    # Wait for state change
    start_time = time.time()
    timeout = 8.0
    
    while time.time() - start_time < timeout:
        screenshot_after = np.array(ImageGrab.grab())
        after_hash = hash(screenshot_after.tobytes())
        
        if after_hash != before_hash:
            # State changed - unlock successful
            return True
        
        time.sleep(0.3)
    
    # State didn't change - unlock failed
    return False


def open_chrome() -> bool:
    """Open Chrome using taskbar-anchored visual system.
    
    This is the single entry point for Chrome automation.
    Replaces all legacy Chrome open + unlock logic.
    
    Returns:
        True if Chrome opened and unlocked, False if failed
    """
    # Step 1: Click Chrome icon
    if not click_chrome_icon():
        raise RuntimeError("Chrome icon not found in taskbar")
    
    time.sleep(1.5)
    
    # Step 2: Handle profile selection
    if not handle_profile_selection():
        raise RuntimeError("Failed to select Chrome profile")
    
    time.sleep(0.5)
    
    # Step 3: Detect and unlock extension
    if not detect_and_unlock_extension():
        raise RuntimeError("Failed to unlock Chrome extension")
    
    return True
