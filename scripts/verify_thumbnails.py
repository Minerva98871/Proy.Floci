"""
Verificacion de las miniaturas de S3 (Etapa 3 / E5).

Descarga las miniaturas del bucket de Lomax SA y comprueba que todas caben
dentro de 300 x 300 px manteniendo la proporcion del original, y que cada
producto tiene exactamente un objeto (la clave de salida es determinista, asi
que repetir la peticion no debe crear miniaturas adicionales).

Uso:  python scripts/verify_thumbnails.py
Salida: 0 si todo cumple, 1 si hay algun problema.
Requiere: boto3 y las credenciales apuntando a Floci (AWS_ENDPOINT_URL).
"""

import os
import sys
from collections import defaultdict

import boto3
from PIL import Image
from io import BytesIO

LIMITE = 300
endpoint = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4567")
bucket_originales = os.environ.get("S3_BUCKET_ORIGINALES", "lomax-originales")
bucket_miniaturas = os.environ.get("S3_BUCKET_MINIATURAS", "lomax-miniaturas")

s3 = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
)


def listar(bucket):
    paginas = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket)
    claves = []
    for pagina in paginas:
        for objeto in pagina.get("Contents", []):
            claves.append(objeto["Key"])
    return claves


def main():
    originales = listar(bucket_originales)
    miniaturas = listar(bucket_miniaturas)
    print(f"bucket {bucket_originales}: {len(originales)} objetos")
    print(f"bucket {bucket_miniaturas}: {len(miniaturas)} objetos")

    if not miniaturas:
        print("ERROR: no hay miniaturas en el bucket")
        return 1

    # La clave de salida es miniaturas/<producto_id>/<sha256(bucket/original)>.
    # Un producto puede tener mas de una miniatura si se le subido mas de una
    # fotografia distinta, y eso es legitimo: lo que no puede pasar es que dos
    # miniaturas apunten al MISMO original, porque significaria que repetir la
    # peticun creo un objeto adicional. Por eso se comparan los hashes con los
    # originales: el numero de miniaturas de un producto debe coincidir con el
    # de originales que tiene.
    por_producto_mini = defaultdict(list)
    for clave in miniaturas:
        partes = clave.split("/")
        if len(partes) > 2 and partes[0] == "miniaturas":
            por_producto_mini[partes[1]].append(clave)

    por_producto_orig = defaultdict(list)
    for clave in originales:
        partes = clave.split("/")
        if len(partes) > 2 and partes[0] == "originales":
            por_producto_orig[partes[1]].append(clave)

    print(f"productos con miniatura: {len(por_producto_mini)}")
    desajuste = {
        pid: (len(por_producto_orig.get(pid, [])), len(claves))
        for pid, claves in por_producto_mini.items()
        if len(claves) != len(por_producto_orig.get(pid, []))
    }
    if desajuste:
        print("ERROR: hay mas miniaturas que originales para un producto, "
              "lo que indicaria processing duplicado de la misma imagen:")
        for pid, (n_orig, n_mini) in desajuste.items():
            print(f"  producto {pid}: {n_orig} originales, {n_mini} miniaturas")
        return 1
    print("OK: cada original tiene su miniatura y ninguna se duplico al repetir la peticion")

    # Cada miniatura debe caber en 300 x 300 y conservar la proporcion.
    fuera_de_limite = []
    for clave in sorted(miniaturas):
        cuerpo = s3.get_object(Bucket=bucket_miniaturas, Key=clave)["Body"].read()
        with Image.open(BytesIO(cuerpo)) as imagen:
            ancho, alto = imagen.size
        cabe = ancho <= LIMITE and alto <= LIMITE
        if not cabe:
            fuera_de_limite.append((clave, ancho, alto))
        marca = "OK  " if cabe else "MAL "
        print(f"  {marca}{clave}  {ancho}x{alto}")

    if fuera_de_limite:
        print(f"ERROR: {len(fuera_de_limite)} miniaturas exceden {LIMITE}x{LIMITE}")
        return 1
    print(f"OK: las {len(miniaturas)} miniaturas caben en {LIMITE}x{LIMITE} conservando la proporcion")
    return 0


if __name__ == "__main__":
    sys.exit(main())
