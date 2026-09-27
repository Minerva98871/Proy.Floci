import hashlib
import io
import os

import boto3
from PIL import Image, ImageOps
from botocore.config import Config


ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL", "http://floci:4566")
ORIGINALS_BUCKET = os.environ["ORIGINALS_BUCKET"]
THUMBNAILS_BUCKET = os.environ["THUMBNAILS_BUCKET"]
DYNAMODB_TABLE = os.environ["DYNAMODB_TABLE"]
MAX_IMAGE_BYTES = 5 * 1024 * 1024

aws_config = Config(s3={"addressing_style": "path"})
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL, config=aws_config)
dynamodb = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
products = dynamodb.Table(DYNAMODB_TABLE)


def thumbnail_key(product_id, source_bucket, source_key):
    identity = f"{source_bucket}/{source_key}".encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()
    return f"miniaturas/{product_id}/{digest}.jpg"


def set_status(product_id, source_key, status, output_key=None, error=None):
    expression_values = {":source": source_key, ":status": status}
    set_fields = ["imagen_original_key = :source", "imagen_estado = :status"]
    remove_fields = []

    if output_key is not None:
        expression_values[":thumbnail"] = output_key
        set_fields.append("miniatura_key = :thumbnail")
    if error is not None:
        expression_values[":error"] = error[:500]
        set_fields.append("imagen_error = :error")

    if output_key is None:
        remove_fields.append("miniatura_key")
    if error is None:
        remove_fields.append("imagen_error")

    update_expression = "SET " + ", ".join(set_fields)
    if remove_fields:
        update_expression += " REMOVE " + ", ".join(remove_fields)
    products.update_item(
        Key={"producto_id": int(product_id)},
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_values,
    )


def make_thumbnail(image_bytes):
    with Image.open(io.BytesIO(image_bytes)) as source:
        if source.format not in ("JPEG", "PNG"):
            raise ValueError("Formato no permitido: solo JPEG o PNG.")
        source.verify()

    with Image.open(io.BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source)
        original_size = image.size
        image.thumbnail((300, 300), Image.Resampling.LANCZOS)
        thumbnail_size = image.size
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=88, optimize=True)
        return output.getvalue(), original_size, thumbnail_size


def handler(event, context):
    product_id = str(event.get("producto_id", "")).strip()
    source_bucket = event.get("bucket")
    source_key = event.get("clave_original")
    if not product_id or not product_id.isdigit() or not source_bucket or not source_key:
        raise ValueError("Se requieren producto_id numerico, bucket y clave_original.")
    if source_bucket != ORIGINALS_BUCKET:
        raise ValueError("El bucket recibido no es el bucket configurado de originales.")

    output_key = thumbnail_key(product_id, source_bucket, source_key)
    try:
        set_status(product_id, source_key, "PENDIENTE")
        s3.delete_object(Bucket=THUMBNAILS_BUCKET, Key=output_key)

        metadata = s3.head_object(Bucket=source_bucket, Key=source_key)
        if metadata["ContentLength"] > MAX_IMAGE_BYTES:
            raise ValueError("La imagen supera el limite de 5 MiB.")

        response = s3.get_object(Bucket=source_bucket, Key=source_key)
        image_bytes = response["Body"].read(MAX_IMAGE_BYTES + 1)
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise ValueError("La imagen supera el limite de 5 MiB.")

        thumbnail_bytes, original_size, thumbnail_size = make_thumbnail(image_bytes)
        s3.put_object(
            Bucket=THUMBNAILS_BUCKET,
            Key=output_key,
            Body=thumbnail_bytes,
            ContentType="image/jpeg",
        )
        set_status(product_id, source_key, "LISTA", output_key=output_key)
        return {
            "estado": "LISTA",
            "producto_id": product_id,
            "imagen_original_key": source_key,
            "miniatura_key": output_key,
            "original_bytes": len(image_bytes),
            "miniatura_bytes": len(thumbnail_bytes),
            "dimensiones_original": {
                "ancho": original_size[0],
                "alto": original_size[1],
            },
            "dimensiones_miniatura": {
                "ancho": thumbnail_size[0],
                "alto": thumbnail_size[1],
            },
        }
    except Exception as error:
        s3.delete_object(Bucket=THUMBNAILS_BUCKET, Key=output_key)
        set_status(product_id, source_key, "ERROR", error=str(error))
        return {
            "estado": "ERROR",
            "producto_id": product_id,
            "imagen_original_key": source_key,
            "error": str(error),
        }