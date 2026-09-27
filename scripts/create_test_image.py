import os
import sys

from PIL import Image, ImageDraw


output_path = sys.argv[1]
os.makedirs(os.path.dirname(output_path), exist_ok=True)
image = Image.new("RGB", (1200, 800), "white")
draw = ImageDraw.Draw(image)
draw.rectangle((0, 0, 599, 399), fill=(30, 125, 170))
draw.rectangle((600, 0, 1199, 399), fill=(238, 165, 55))
draw.rectangle((0, 400, 599, 799), fill=(80, 155, 105))
draw.rectangle((600, 400, 1199, 799), fill=(190, 75, 75))
draw.text((80, 80), "LOMAX 1200 x 800", fill="white")
image_format = "PNG" if output_path.lower().endswith(".png") else "JPEG"
if image_format == "PNG":
	image.save(output_path, format=image_format)
else:
	image.save(output_path, format=image_format, quality=90)
print(f"Creada: {output_path} ({image.width}x{image.height})")