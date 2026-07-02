import mss
import cv2
import numpy as np
import pytesseract
import time

# ---------------- CONFIG ----------------
ROI = {"top": 100, "left": 100, "width": 300, "height": 300}
MIN_AREA = 200
MAX_AREA = 20000
DIFF_THRESHOLD = 25
FRAME_DELAY = 0.01

seen = set()

print("Starting ROI change + OCR detector...")

# ---------------------------------------

def clean_text(text: str) -> str:
    text = text.strip()
    if len(text) < 3:
        return ""
    if sum(c.isalnum() for c in text) < 3:
        return ""
    return text


with mss.mss() as sct:
    prev = np.array(sct.grab(ROI))
    prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)

    start = time.time()

    for _ in range(400):
        curr = np.array(sct.grab(ROI))
        curr_gray = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY)

        diff = cv2.absdiff(prev_gray, curr_gray)
        _, mask = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)

        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_OPEN,
            np.ones((3, 3), np.uint8),
            iterations=2,
        )

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < MIN_AREA or area > MAX_AREA:
                continue

            x, y, w, h = cv2.boundingRect(cnt)

            region = curr[y:y+h, x:x+w]
            if region.size == 0:
                continue

            # ---- OCR PREPROCESS ----
            gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            _, gray = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )

            text = pytesseract.image_to_string(
                gray,
                config="--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:@._-"
            )

            text = clean_text(text)
            if not text:
                continue

            key = (x // 10, y // 10, text)
            if key in seen:
                continue

            seen.add(key)
            print(f"OCR @ ({x},{y},{w},{h}) → '{text}'")

        prev_gray = curr_gray
        time.sleep(FRAME_DELAY)

end = time.time()
print("Done.")
print("Time:", round(end - start, 2), "seconds")