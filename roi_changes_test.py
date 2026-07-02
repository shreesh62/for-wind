import mss
import cv2
import numpy as np
import time

print("Starting ROI change detector...")

with mss.mss() as sct:
    roi = {"top": 100, "left": 100, "width": 300, "height": 300}

    prev = np.array(sct.grab(roi))
    prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)

    for _ in range(300):
        curr = np.array(sct.grab(roi))
        curr_gray = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY)

        diff = cv2.absdiff(prev_gray, curr_gray)
        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

        kernel = np.ones((3, 3), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)

        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 150 or area > 15000:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            print(f"Change detected at ROI coords: x={x}, y={y}, w={w}, h={h}")
            break

        prev_gray = curr_gray
        time.sleep(0.01)

print("Done.")