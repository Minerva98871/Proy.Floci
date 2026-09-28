import boto3
import logging
from io import BytesIO
from config import Config

logger = logging.getLogger(__name__)

class S3Service:
    """Gestor de operaciones en S3"""
    
    @staticmethod
    def get_s3_client():
        """Obtiene cliente S3"""
        return boto3.client(
            's3',
            endpoint_url=Config.S3_ENDPOINT,
            region_name=Config.AWS_REGION,
            aws_access_key_id='test',
            aws_secret_access_key='test'
        )
    
    @staticmethod
    def guardar_original(producto_id, imagen_bytes, extension):
        """Guarda la imagen original en S3"""
        try:
            s3 = S3Service.get_s3_client()
            
            # Clave: producto_{id}.{ext}
            key = f"producto_{producto_id}.{extension.lower()}"
            
            s3.put_object(
                Bucket=Config.S3_BUCKET_ORIGINALES,
                Key=key,
                Body=imagen_bytes,
                ContentType=f"image/{extension.lower()}"
            )
            
            logger.info(f"Imagen original guardada: {key}")
            return key
        except Exception as e:
            logger.error(f"Error guardando imagen original: {e}")
            return None
    
    @staticmethod
    def obtener_miniatura(producto_id):
        """Obtiene la miniatura desde S3"""
        try:
            s3 = S3Service.get_s3_client()
            
            # Clave: miniatura_{id}.jpg
            key = f"miniatura_{producto_id}.jpg"
            
            response = s3.get_object(
                Bucket=Config.S3_BUCKET_MINIATURAS,
                Key=key
            )
            
            imagen_bytes = response['Body'].read()
            content_type = response.get('ContentType', 'image/jpeg')
            
            return imagen_bytes, content_type
        except s3.exceptions.NoSuchKey:
            logger.warning(f"Miniatura no encontrada: {key}")
            return None, None
        except Exception as e:
            logger.error(f"Error obteniendo miniatura: {e}")
            return None, None
    
    @staticmethod
    def obtener_original(producto_id, extension):
        """Obtiene la imagen original desde S3"""
        try:
            s3 = S3Service.get_s3_client()
            
            key = f"producto_{producto_id}.{extension.lower()}"
            
            response = s3.get_object(
                Bucket=Config.S3_BUCKET_ORIGINALES,
                Key=key
            )
            
            return response['Body'].read()
        except Exception as e:
            logger.error(f"Error obteniendo original: {e}")
            return None
    
    @staticmethod
    def listar_originales():
        """Lista todas las imágenes originales en S3"""
        try:
            s3 = S3Service.get_s3_client()
            
            response = s3.list_objects_v2(
                Bucket=Config.S3_BUCKET_ORIGINALES
            )
            
            objetos = []
            if 'Contents' in response:
                objetos = [obj['Key'] for obj in response['Contents']]
            
            return objetos
        except Exception as e:
            logger.error(f"Error listando originales: {e}")
            return []
