import boto3
import json
import logging
from config import Config

logger = logging.getLogger(__name__)

class DynamoDBService:
    """Gestor de operaciones en DynamoDB"""
    
    @staticmethod
    def get_dynamodb_resource():
        """Obtiene recurso DynamoDB"""
        return boto3.resource(
            'dynamodb',
            endpoint_url=Config.DYNAMODB_ENDPOINT,
            region_name=Config.AWS_REGION,
            aws_access_key_id='test',
            aws_secret_access_key='test'
        )
    
    @staticmethod
    def guardar_atributos(producto_id, atributos):
        """Guarda atributos variables de un producto en DynamoDB"""
        try:
            dynamodb = DynamoDBService.get_dynamodb_resource()
            table = dynamodb.Table(Config.DYNAMODB_TABLE)
            
            # Estructura: { "producto_id": id, "atributos": {...}, "estado_imagen": "PENDIENTE" }
            item = {
                'producto_id': int(producto_id),
                'atributos': atributos,
                'estado_imagen': 'PENDIENTE'
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
    def actualizar_estado_imagen(producto_id, estado_imagen, imagen_original_key=None, miniatura_key=None):
        """Actualiza el estado de procesamiento de la imagen"""
        try:
            dynamodb = DynamoDBService.get_dynamodb_resource()
            table = dynamodb.Table(Config.DYNAMODB_TABLE)
            
            update_expr = "SET estado_imagen = :estado"
            expr_values = {":estado": estado_imagen}
            
            if imagen_original_key:
                update_expr += ", imagen_original_key = :original"
                expr_values[":original"] = imagen_original_key
            
            if miniatura_key:
                update_expr += ", miniatura_key = :miniatura"
                expr_values[":miniatura"] = miniatura_key
            
            table.update_item(
                Key={'producto_id': int(producto_id)},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values
            )
            logger.info(f"Estado imagen actualizado para {producto_id}: {estado_imagen}")
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
