"""
Genera una fotografia por cada producto del catalogo de Lomax SA.

La E2 pide al menos 20 productos publicados con una fotografia cada uno. Las
imagenes se generan con dimensiones y colores distintos para que la miniatura
de 300 x 300 pixeles tenga que escalar de verdad, y para que se vea en el
catalogo que cada producto tiene su propia imagen y no una copia.

Uso (dentro de la imagen lomax-image-tools):

    python /tools/generate_product_images.py /catalogo/productos.json /catalogo/salida

El primer argumento es un JSON con la lista de productos (codigo, nombre,
categoria). El segundo es el directorio donde se escriben los JPEG.
"""

import json
import os
import random
import sys

from PIL import Image, ImageDraw

# Paleta por categoria, para que el catalogo sea reconocible de un vistazo.
COLOR_POR_CATEGORIA = {
    "Electrónica": (30, 125, 170),
    "Hogar": (238, 165, 55),
    "Oficina": (80, 105, 155),
    "Accesorios": (150, 80, 160),
    "Computación": (80, 155, 105),
}

# Proporciones variadas: unas panoramicas, otras casi cuadradas, una
# vertical. Asi se comprueba que la miniatura respeta la proporcion y cabe
# dentro de 300 x 300 sin deformarse.
PROPORCIONES = [
    (1200, 800),
    (800, 1200),
    (1000, 1000),
    (1600, 900),
    (900, 1600),
]


def dibujar_producto(ruta, nombre, categoria, seed):
    """Dibuja una fotografia sintetica con el nombre del producto."""
    aleatorio = random.Random(seed)
    ancho, alto = PROPORCIONES[seed % len(PROPORCIONES)]
    color_base = COLOR_POR_CATEGORIA.get(categoria, (90, 90, 110))

    imagen = Image.new("RGB", (ancho, alto), tuple(
        min(255, c + aleatorio.randint(-18, 18)) for c in color_base
    ))
    dibujo = ImageDraw.Draw(imagen)

    # Fondo degradado en bandas para que la miniatura no sea un bloque plano.
    bandas = 6
    for i in range(bandas):
        t = i / max(1, bandas - 1)
        tono = tuple(
            int(color_base[c] * (1 - 0.35 * t) + 255 * 0.35 * t * 0.5) for c in range(3)
        )
        y0 = int(alto * i / bandas)
        y1 = int(alto * (i + 1) / bandas)
        dibujo.rectangle((0, y0, ancho, y1), fill=tono)

    # Silueta del producto: un cuerpo central con un pie, con la proporción
    # de la imagen, para que al reducirse siga leyendose como un objeto.
    margen_x = int(ancho * 0.22)
    margen_y = int(alto * 0.18)
    dibujo.rounded_rectangle(
        (margen_x, margen_y, ancho - margen_x, alto - int(alto * 0.26)),
        radius=max(12, ancho // 30),
        fill=tuple(min(255, c + 60) for c in color_base),
        outline=(255, 255, 255),
        width=max(2, ancho // 300),
    )

    # Detalle: una "pantalla" y una "base".
    dibujo.rounded_rectangle(
        (margen_x + ancho // 12, margen_y + alto // 12,
         ancho - margen_x - ancho // 12, alto - int(alto * 0.42)),
        radius=max(8, ancho // 40),
        fill=(24, 30, 40),
    )
    dibujo.rectangle(
        (ancho // 3, alto - int(alto * 0.24), ancho * 2 // 3, alto - int(alto * 0.20)),
        fill=(240, 240, 245),
    )

    # Etiqueta con el nombre del producto.
    try:
        from PIL import ImageFont
        fuente = ImageFont.truetype("DejaVuSans-Bold.ttf", max(16, ancho // 34))
    except Exception:
        fuente = ImageFont.load_default()
    dibujo.text(
        (margen_x + ancho // 12, alto - int(alto * 0.16)),
        nombre,
        fill=(255, 255, 255),
        font=fuente,
    )
    dibujo.text(
        (margen_x + ancho // 12, alto - int(alto * 0.10)),
        f"Lomax SA - {categoria}",
        fill=(235, 235, 240),
        font=fuente,
    )

    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    # calidad alta para que el original pese lo bastante como para que la
    # miniatura sea una reduccion real y no una copia.
    imagen.save(ruta, format="JPEG", quality=88)
    return ancho, alto


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    catalogo = json.load(open(sys.argv[1], encoding="utf-8"))
    directorio = sys.argv[2]
    os.makedirs(directorio, exist_ok=True)

    for indice, producto in enumerate(catalogo):
        codigo = producto["codigo"]
        ruta = os.path.join(directorio, f"{codigo}.jpg")
        ancho, alto = dibujar_producto(
            ruta,
            producto.get("nombre", codigo),
            producto.get("categoria", "General"),
            indice,
        )
        print(f"  {codigo}  {ancho}x{alto}  ->  {os.path.basename(ruta)}")

    print(f"Generadas {len(catalogo)} imagenes en {directorio}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
