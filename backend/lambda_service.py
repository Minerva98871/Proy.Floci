import boto3
import json
import logging
from config import Config

logger = logging.getLogger(__name__)

class LambdaService:
    """Gestor para invocar funciones Lambda"""
    
    @staticmethod
    def get_lambda_client():
        """Obtiene cliente Lambda"""
        return boto3.client(
            'lambda',
            endpoint_url=Config.LAMBDA_ENDPOINT,
            region_name=Config.AWS_REGION,
            aws_access_key_id='test',
            aws_secret_access_key='test'
        )
    
    @staticmethod
    def invocar_procesar_imagen(producto_id, imagen_original_key):
        """Invoca Lambda de forma síncrona para procesar la imagen"""
        try:
            lambda_client = LambdaService.get_lambda_client()
            
            # Evento que recibe Lambda
            payload = {
                'producto_id': str(producto_id),
                'imagen_original_key': imagen_original_key,
                'bucket_originales': Config.S3_BUCKET_ORIGINALES,
                'bucket_miniaturas': Config.S3_BUCKET_MINIATURAS
            }
            
            # Invocación síncrona
            response = lambda_client.invoke(
                FunctionName=Config.LAMBDA_FUNCTION,
                InvocationType='RequestResponse',  # Síncrona
                Payload=json.dumps(payload)
            )
            
            # Leer respuesta
            respuesta_lambda = json.loads(response['Payload'].read().decode())
            
            logger.info(f"Lambda invocada para producto {producto_id}: {respuesta_lambda}")
            
            return respuesta_lambda
        except Exception as e:
            logger.error(f"Error invocando Lambda: {e}")
            return {
                'statusCode': 503,
                'body': {'error': 'Error invocando Lambda', 'details': str(e)}
            }
