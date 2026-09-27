import json
import sys

from PIL import Image


result = {}
for path in sys.argv[1:]:
    with Image.open(path) as image:
        result[path.rsplit("/", 1)[-1]] = {
            "ancho": image.width,
            "alto": image.height,
            "formato": image.format,
        }
print(json.dumps(result, ensure_ascii=False, indent=2))