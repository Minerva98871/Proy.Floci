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
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY
        )

    @staticmethod
    def invocar_procesar_imagen(producto_id, imagen_original_key):
        """
        Invoca Lambda de forma síncrona para procesar la imagen.

        Contrato esperado por lambda/handler.py:
          evento  -> {producto_id, bucket, clave_original}
          respuesta-> {estado, producto_id, imagen_original_key, miniatura_key, ...}

        Si la invocación falla a nivel de transporte o la función lanza una
        excepcion no capturada, devuelve estado ERROR con el detalle del fallo.
        """
        payload = {
            'producto_id': str(producto_id),
            'bucket': Config.S3_BUCKET_ORIGINALES,
            'clave_original': imagen_original_key
        }

        try:
            response = LambdaService.get_lambda_client().invoke(
                FunctionName=Config.LAMBDA_FUNCTION,
                InvocationType='RequestResponse',  # Síncrona
                Payload=json.dumps(payload)
            )
        except Exception as e:
            logger.error(f"Error invocando Lambda: {e}")
            return {
                'estado': 'ERROR',
                'producto_id': str(producto_id),
                'imagen_original_key': imagen_original_key,
                'error': f'No se pudo invocar Lambda: {e}'
            }

        # Fallo de transporte (payload malformado, runtime caido, etc.)
        error_transporte = response.get('FunctionError')
        if error_transporte:
            detalle = response.get('Payload').read().decode('utf-8', errors='replace')
            logger.error(f"Lambda devolvio FunctionError={error_transporte}: {detalle}")
            return {
                'estado': 'ERROR',
                'producto_id': str(producto_id),
                'imagen_original_key': imagen_original_key,
                'error': f'Lambda fallo ({error_transporte}): {detalle[:500]}'
            }

        crudo = response['Payload'].read().decode('utf-8')
        try:
            resultado = json.loads(crudo)
        except json.JSONDecodeError as e:
            logger.error(f"Respuesta de Lambda no es JSON valido: {crudo[:200]}")
            return {
                'estado': 'ERROR',
                'producto_id': str(producto_id),
                'imagen_original_key': imagen_original_key,
                'error': f'Respuesta de Lambda ilegible: {e}'
            }

        # El handler no siempre envuelve en statusCode/body; normalizamos aqui.
        cuerpo = resultado.get('body', resultado)
        if isinstance(cuerpo, str):
            try:
                cuerpo = json.loads(cuerpo)
            except json.JSONDecodeError:
                cuerpo = {}
        if not isinstance(cuerpo, dict):
            cuerpo = {}

        estado = cuerpo.get('estado', 'ERROR')
        if estado != 'LISTA':
            cuerpo.setdefault('error', 'Lambda no devolvio una miniatura')

        logger.info(f"Lambda invocada para producto {producto_id}: estado={estado}")
        return cuerpo
