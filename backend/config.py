import os

# Los valores por defecto coinciden con los que crean scripts/setup.ps1 y
# scripts/stage3.ps1. Si cambian esos scripts, cambia tambien estos defaults.
ENDPOINT_LOCAL = 'http://localhost:4567'


class Config:
    """Configuración base"""

    DEBUG = os.getenv('FLASK_DEBUG', 'False') == 'True'
    TESTING = False

    # RDS MySQL - Usar variables de entorno del docker-compose
    RDS_HOST = os.getenv('RDS_HOST', 'localhost')
    RDS_PORT = int(os.getenv('RDS_PORT', 3306))
    RDS_USER = os.getenv('RDS_USER', 'lomax')
    RDS_PASSWORD = os.getenv('RDS_PASSWORD', 'LomaxLocal2026!')
    RDS_DATABASE = os.getenv('RDS_DATABASE', 'lomax_catalogo')

    # AWS S3
    S3_ENDPOINT = os.getenv('S3_ENDPOINT', ENDPOINT_LOCAL)
    S3_BUCKET_ORIGINALES = os.getenv('S3_BUCKET_ORIGINALES', 'lomax-originales')
    S3_BUCKET_MINIATURAS = os.getenv('S3_BUCKET_MINIATURAS', 'lomax-miniaturas')
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

    # Prefijo de las imagenes originales dentro del bucket.
    # Debe coincidir con la convencion de scripts/stage3.ps1: originales/<id>/<archivo>
    S3_ORIGINALES_PREFIX = os.getenv('S3_ORIGINALES_PREFIX', 'originales')

    # DynamoDB
    DYNAMODB_ENDPOINT = os.getenv('DYNAMODB_ENDPOINT', ENDPOINT_LOCAL)
    DYNAMODB_TABLE = os.getenv('DYNAMODB_TABLE', 'LomaxAtributos')

    # Lambda
    LAMBDA_ENDPOINT = os.getenv('LAMBDA_ENDPOINT', ENDPOINT_LOCAL)
    LAMBDA_FUNCTION = os.getenv('LAMBDA_FUNCTION', 'lomax-thumbnail')
    LAMBDA_TIMEOUT = int(os.getenv('LAMBDA_TIMEOUT', 60))

    # Validación de imágenes
    MAX_IMAGE_SIZE = int(os.getenv('MAX_IMAGE_SIZE', 5242880))  # 5 MiB
    ALLOWED_IMAGE_FORMATS = {'jpeg', 'jpg', 'png'}

    # Credenciales para el emulador local de Floci
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', 'test')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', 'test')
