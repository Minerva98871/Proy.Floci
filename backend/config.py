import os

class Config:
    """Configuración base"""
    DEBUG = os.getenv('FLASK_DEBUG', 'False') == 'True'
    TESTING = False
    
    # RDS MySQL - Usar variables de entorno del docker-compose
    RDS_HOST = os.getenv('RDS_HOST', 'localhost')
    RDS_PORT = int(os.getenv('RDS_PORT', 3306))
    RDS_USER = os.getenv('RDS_USER', 'admin')
    RDS_PASSWORD = os.getenv('RDS_PASSWORD', 'Admin1234!')
    RDS_DATABASE = os.getenv('RDS_DATABASE', 'catalogo_productos')
    
    # AWS S3
    S3_ENDPOINT = os.getenv('S3_ENDPOINT', 'http://localhost:4566')
    S3_BUCKET_ORIGINALES = os.getenv('S3_BUCKET_ORIGINALES', 'lomax-originales')
    S3_BUCKET_MINIATURAS = os.getenv('S3_BUCKET_MINIATURAS', 'lomax-miniaturas')
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    
    # DynamoDB
    DYNAMODB_ENDPOINT = os.getenv('DYNAMODB_ENDPOINT', 'http://localhost:4566')
    DYNAMODB_TABLE = os.getenv('DYNAMODB_TABLE', 'LomaxAtributos')
    
    # Lambda
    LAMBDA_ENDPOINT = os.getenv('LAMBDA_ENDPOINT', 'http://localhost:4566')
    LAMBDA_FUNCTION = os.getenv('LAMBDA_FUNCTION', 'lomax-thumbnail')
    
    # Validación de imágenes
    MAX_IMAGE_SIZE = int(os.getenv('MAX_IMAGE_SIZE', 5242880))  # 5 MB
    ALLOWED_IMAGE_FORMATS = {'jpeg', 'jpg', 'png'}
    
    # Flask
    JSON_SORT_KEYS = False