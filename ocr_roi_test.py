import pytesseract
import cv2
from PIL import Image
import numpy as np

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"

# Load image
img = cv2.imread("test.png")

# Define ROI manually (tweak these if needed)
# (x, y, width, height)
x, y, w, h = 0, 0, 400, 200
roi = img[y:y+h, x:x+w]

# Preprocess for OCR
gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

# OCR
text = pytesseract.image_to_string(gray, config="--psm 6")

print("ROI OCR OUTPUT:")
print(text)