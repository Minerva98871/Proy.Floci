import boto3
import logging
import re
from config import Config

logger = logging.getLogger(__name__)


def sanitizar_nombre(nombre):
    """Reduce un nombre de archivo a un token seguro para usarlo como clave S3."""
    nombre = re.sub(r'[^A-Za-z0-9._-]+', '_', (nombre or '').strip())
    return nombre.lstrip('.') or 'imagen'


class S3Service:
    """Gestor de operaciones en S3"""

    @staticmethod
    def get_s3_client():
        """Obtiene cliente S3"""
        return boto3.client(
            's3',
            endpoint_url=Config.S3_ENDPOINT,
            region_name=Config.AWS_REGION,
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY
        )

    @staticmethod
    def construir_clave_original(producto_id, nombre_archivo):
        """
        Clave del original: originales/<producto_id>/<archivo>

        Usa el mismo prefijo que scripts/stage3.ps1 para que las imagenes de
        ambas etapas convivan en el bucket lomax-originales.
        """
        prefijo = Config.S3_ORIGINALES_PREFIX.strip('/')
        return f"{prefijo}/{producto_id}/{sanitizar_nombre(nombre_archivo)}"

    @staticmethod
    def guardar_original(producto_id, imagen_bytes, nombre_archivo, content_type):
        """Guarda la imagen original en S3 y devuelve su clave"""
        try:
            key = S3Service.construir_clave_original(producto_id, nombre_archivo)

            S3Service.get_s3_client().put_object(
                Bucket=Config.S3_BUCKET_ORIGINALES,
                Key=key,
                Body=imagen_bytes,
                ContentType=content_type
            )

            logger.info(f"Imagen original guardada: {key}")
            return key
        except Exception as e:
            logger.error(f"Error guardando imagen original: {e}")
            return None

    @staticmethod
    def obtener_miniatura(miniatura_key):
        """
        Descarga la miniatura usando la clave exacta registrada en DynamoDB.

        La clave la determina lambda/handler.py como
        miniaturas/<producto_id>/<sha256(bucket/clave)>.jpg, por lo que no puede
        reconstruirse aquí: hay que leerla del item de DynamoDB.
        """
        if not miniatura_key:
            return None, None

        try:
            response = S3Service.get_s3_client().get_object(
                Bucket=Config.S3_BUCKET_MINIATURAS,
                Key=miniatura_key
            )

            imagen_bytes = response['Body'].read()
            content_type = response.get('ContentType', 'image/jpeg')
            return imagen_bytes, content_type
        except Exception as e:
            codigo = e.response['Error']['Code'] if hasattr(e, 'response') else ''
            if codigo in ('NoSuchKey', '404', 'NoSuchBucket'):
                logger.warning(f"Miniatura no encontrada en S3: {miniatura_key}")
            else:
                logger.error(f"Error obteniendo miniatura {miniatura_key}: {e}")
            return None, None

    @staticmethod
    def obtener_original(producto_id, nombre_archivo):
        """Obtiene la imagen original desde S3"""
        try:
            key = S3Service.construir_clave_original(producto_id, nombre_archivo)
            response = S3Service.get_s3_client().get_object(
                Bucket=Config.S3_BUCKET_ORIGINALES,
                Key=key
            )
            return response['Body'].read()
        except Exception as e:
            logger.error(f"Error obteniendo original: {e}")
            return None

    @staticmethod
    def listar_originales(prefijo=''):
        """Lista las claves de imagenes originales en S3"""
        try:
            cliente = S3Service.get_s3_client()
        except Exception as e:
            logger.error(f"Error creando cliente S3: {e}")
            return []

        claves = []
        paginador = cliente.get_paginator('list_objects_v2')
        try:
            for pagina in paginador.paginate(
                Bucket=Config.S3_BUCKET_ORIGINALES,
                Prefix=f"{Config.S3_ORIGINALES_PREFIX.strip('/')}/{prefijo}"
            ):
                claves.extend(obj['Key'] for obj in pagina.get('Contents', []))
        except Exception as e:
            logger.error(f"Error listando originales: {e}")
            return []
        return claves
