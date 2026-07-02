import clip
import torch
from PIL import Image

device = "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)

image = preprocess(Image.open("test.png")).unsqueeze(0).to(device)

labels = [
    "a login screen",
    "a chat application",
    "a settings page",
    "random text"
]

text = clip.tokenize(labels).to(device)

with torch.no_grad():
    image_features = model.encode_image(image)
    text_features = model.encode_text(text)

    similarity = (image_features @ text_features.T).softmax(dim=-1)

for label, score in zip(labels, similarity[0]):
    print(label, round(float(score), 3))