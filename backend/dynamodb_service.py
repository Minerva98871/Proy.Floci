import boto3
import logging
from config import Config

logger = logging.getLogger(__name__)

# Estados posibles del atributo imagen_estado. Deben coincidir con los que
# escribe lambda/handler.py (PENDIENTE, LISTA, ERROR) y con el ENUM de
# database/schema.sql para el estado del producto en RDS.
ESTADO_SIN_PROCESAR = 'PENDIENTE'
ESTADO_PROCESANDO = 'PROCESANDO'
ESTADO_LISTA = 'LISTA'
ESTADO_ERROR = 'ERROR'


class DynamoDBService:
    """Gestor de operaciones en DynamoDB"""

    @staticmethod
    def get_dynamodb_resource():
        """Obtiene recurso DynamoDB"""
        return boto3.resource(
            'dynamodb',
            endpoint_url=Config.DYNAMODB_ENDPOINT,
            region_name=Config.AWS_REGION,
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY
        )

    @staticmethod
    def guardar_atributos(producto_id, codigo, atributos):
        """
        Guarda los atributos variables de un producto en DynamoDB.

        Crea el item con la misma forma que usa scripts/stage3.ps1:
        producto_id (N), codigo (S), atributos (M), imagen_estado (S).
        """
        try:
            dynamodb = DynamoDBService.get_dynamodb_resource()
            table = dynamodb.Table(Config.DYNAMODB_TABLE)

            item = {
                'producto_id': int(producto_id),
                'codigo': codigo,
                'atributos': atributos,
                'imagen_estado': ESTADO_SIN_PROCESAR
            }

            table.put_item(Item=item)
            logger.info(f"Atributos guardados para producto {producto_id}")
            return True
        except Exception as e:
            logger.error(f"Error guardando atributos en DynamoDB: {e}")
            return False

    @staticmethod
    def obtener_atributos(producto_id):
        """Obtiene atributos de un producto"""
        try:
            dynamodb = DynamoDBService.get_dynamodb_resource()
            table = dynamodb.Table(Config.DYNAMODB_TABLE)

            response = table.get_item(Key={'producto_id': int(producto_id)})

            if 'Item' in response:
                return response['Item']
            return None
        except Exception as e:
            logger.error(f"Error obteniendo atributos: {e}")
            return None

    @staticmethod
    def actualizar_estado_imagen(producto_id, imagen_estado, imagen_original_key=None,
                                 miniatura_key=None, imagen_error=None):
        """
        Actualiza el estado de procesamiento de la imagen.

        Usa el atributo imagen_estado, que es el nombre que escriben tanto
        lambda/handler.py como scripts/stage3.ps1. Cuando el estado no es LISTA
        se elimina miniatura_key para no dejar una referencia a una miniatura
        que ya no existe o que nunca se genero.
        """
        try:
            dynamodb = DynamoDBService.get_dynamodb_resource()
            table = dynamodb.Table(Config.DYNAMODB_TABLE)

            set_fields = ['imagen_estado = :estado']
            expr_values = {':estado': imagen_estado}
            remove_fields = []

            if imagen_original_key:
                set_fields.append('imagen_original_key = :original')
                expr_values[':original'] = imagen_original_key

            if miniatura_key:
                set_fields.append('miniatura_key = :miniatura')
                expr_values[':miniatura'] = miniatura_key
            elif imagen_estado != ESTADO_LISTA:
                remove_fields.append('miniatura_key')

            if imagen_error:
                set_fields.append('imagen_error = :error')
                expr_values[':error'] = str(imagen_error)[:500]
            else:
                remove_fields.append('imagen_error')

            update_expression = 'SET ' + ', '.join(set_fields)
            if remove_fields:
                update_expression += ' REMOVE ' + ', '.join(remove_fields)

            table.update_item(
                Key={'producto_id': int(producto_id)},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expr_values
            )
            logger.info(f"Estado imagen de {producto_id} -> {imagen_estado}")
            return True
        except Exception as e:
            logger.error(f"Error actualizando estado imagen: {e}")
            return False

    @staticmethod
    def existe_item(producto_id):
        """Verifica si existe un item en DynamoDB"""
        try:
            dynamodb = DynamoDBService.get_dynamodb_resource()
            table = dynamodb.Table(Config.DYNAMODB_TABLE)

            response = table.get_item(Key={'producto_id': int(producto_id)})
            return 'Item' in response
        except Exception as e:
            logger.error(f"Error verificando existencia: {e}")
            return False
