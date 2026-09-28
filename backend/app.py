from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import logging
import os
from datetime import datetime
from io import BytesIO

from config import Config
from database import RDSDatabase
from dynamodb_service import DynamoDBService
from s3_service import S3Service
from lambda_service import LambdaService

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear app Flask
app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# ============================================================================
# ENDPOINT 1: GET /categorias
# Retorna: 200 con categorías de RDS
# ============================================================================
@app.route('/categorias', methods=['GET'])
def get_categorias():
    """GET /categorias - Devuelve las categorías almacenadas en RDS"""
    try:
        categorias, status_code = RDSDatabase.get_categorias()
        if status_code == 200:
            return jsonify({
                'success': True,
                'data': categorias,
                'count': len(categorias)
            }), 200
        else:
            return jsonify(categorias), status_code
    except Exception as e:
        logger.error(f"Error en GET /categorias: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 502


# ============================================================================
# ENDPOINT 2: POST /productos
# Recibe: código, nombre, descripción, precio, categoria_id, atributos
# Retorna: 201 con producto_id y estado PENDIENTE
#          400 si datos inválidos
#          409 si código duplicado
#          400 si categoría no existe
# ============================================================================
@app.route('/productos', methods=['POST'])
def crear_producto():
    """POST /productos - Crea producto en estado PENDIENTE"""
    try:
        data = request.get_json()
        
        # Validar datos requeridos
        campos_requeridos = ['codigo', 'nombre', 'descripcion', 'precio', 'categoria_id', 'atributos']
        if not all(campo in data for campo in campos_requeridos):
            return jsonify({
                'error': 'Datos inválidos',
                'detalle': 'Faltan campos requeridos: ' + ', '.join(campos_requeridos)
            }), 400
        
        codigo = data.get('codigo', '').strip()
        nombre = data.get('nombre', '').strip()
        descripcion = data.get('descripcion', '').strip()
        precio = float(data.get('precio', 0))
        categoria_id = int(data.get('categoria_id', 0))
        atributos = data.get('atributos', {})
        
        # Validaciones
        if not codigo or not nombre or not descripcion:
            return jsonify({'error': 'Datos inválidos', 'detalle': 'Campos vacíos'}), 400
        
        if precio < 0:
            return jsonify({'error': 'Datos inválidos', 'detalle': 'Precio no puede ser negativo'}), 400
        
        if categoria_id <= 0:
            return jsonify({'error': 'Datos inválidos', 'detalle': 'Categoría no válida'}), 400
        
        # Crear producto en RDS
        producto_id, error = RDSDatabase.crear_producto(codigo, nombre, descripcion, precio, categoria_id)
        
        if error:
            if error == "Código duplicado":
                return jsonify({'error': error}), 409
            elif error == "Categoría no existe":
                return jsonify({'error': error}), 400
            else:
                return jsonify({'error': error}), 502
        
        # Guardar atributos en DynamoDB
        atributos_guardados = DynamoDBService.guardar_atributos(producto_id, atributos)
        
        if not atributos_guardados:
            # Si falla DynamoDB, revertir producto en RDS (opcional, pero recomendado)
            logger.warning(f"Fallo al guardar atributos para producto {producto_id}")
            return jsonify({
                'error': 'Fallo al guardar atributos',
                'detalle': 'No se pudieron guardar los atributos en DynamoDB'
            }), 502
        
        # Respuesta exitosa
        return jsonify({
            'success': True,
            'producto_id': producto_id,
            'codigo': codigo,
            'nombre': nombre,
            'estado': 'PENDIENTE',
            'mensaje': 'Producto creado. Carga la imagen para publicarlo.'
        }), 201
    
    except ValueError as e:
        logger.error(f"Error en POST /productos (validación): {e}")
        return jsonify({'error': 'Datos inválidos', 'detalle': str(e)}), 400
    except Exception as e:
        logger.error(f"Error en POST /productos: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 502


# ============================================================================
# ENDPOINT 3: POST /productos/{id}/imagen
# Recibe: imagen JPEG o PNG
# Retorna: 200 con PUBLICADO si todo OK
#          413 si mayor a 5 MB
#          415 si formato no permitido
#          404 si producto no existe
#          502/503 si falla un servicio
# ============================================================================
@app.route('/productos/<int:producto_id>/imagen', methods=['POST'])
def subir_imagen(producto_id):
    """POST /productos/{id}/imagen - Sube imagen y procesa con Lambda"""
    try:
        # Validar que el producto existe
        producto = RDSDatabase.obtener_producto(producto_id)
        if not producto:
            return jsonify({'error': 'Producto no encontrado'}), 404
        
        # Validar que existe en DynamoDB
        if not DynamoDBService.existe_item(producto_id):
            return jsonify({'error': 'Producto no completamente registrado'}), 404
        
        # Validar archivo
        if 'file' not in request.files:
            return jsonify({'error': 'No se envió archivo'}), 400
        
        archivo = request.files['file']
        
        if archivo.filename == '':
            return jsonify({'error': 'Archivo vacío'}), 400
        
        # Validar tamaño
        archivo.seek(0, os.SEEK_END)
        tamaño = archivo.tell()
        archivo.seek(0)
        
        if tamaño > Config.MAX_IMAGE_SIZE:
            return jsonify({
                'error': 'Archivo muy grande',
                'detalle': f'Máximo {Config.MAX_IMAGE_SIZE / 1024 / 1024}MB'
            }), 413
        
        # Validar formato
        extension = archivo.filename.rsplit('.', 1)[-1].lower()
        if extension not in Config.ALLOWED_IMAGE_FORMATS:
            return jsonify({
                'error': 'Formato no permitido',
                'detalle': f'Permitidos: {", ".join(Config.ALLOWED_IMAGE_FORMATS)}'
            }), 415
        
        # Leer contenido
        imagen_bytes = archivo.read()
        
        # Guardar original en S3
        imagen_key = S3Service.guardar_original(producto_id, imagen_bytes, extension)
        
        if not imagen_key:
            return jsonify({'error': 'Error guardando imagen en S3'}), 503
        
        # Actualizar DynamoDB con la clave de original
        DynamoDBService.actualizar_estado_imagen(
            producto_id, 
            'PROCESANDO',
            imagen_original_key=imagen_key
        )
        
        # Invocar Lambda de forma síncrona
        respuesta_lambda = LambdaService.invocar_procesar_imagen(producto_id, imagen_key)
        
        # Procesar respuesta de Lambda
        estado_final = 'PENDIENTE'  # Por defecto
        
        try:
            if isinstance(respuesta_lambda, dict):
                status_lambda = respuesta_lambda.get('statusCode', 500)
                body = respuesta_lambda.get('body', {})
                
                if isinstance(body, str):
                    body = eval(body) if body.startswith('{') else {}
                
                if status_lambda == 200:
                    miniatura_key = body.get('miniatura_key')
                    estado_final = body.get('estado', 'LISTA')
                    
                    # Actualizar DynamoDB con miniatura
                    if miniatura_key:
                        DynamoDBService.actualizar_estado_imagen(
                            producto_id,
                            estado_final,
                            miniatura_key=miniatura_key
                        )
                else:
                    estado_final = 'ERROR'
                    DynamoDBService.actualizar_estado_imagen(producto_id, estado_final)
        except Exception as e:
            logger.warning(f"Error procesando respuesta Lambda: {e}")
            estado_final = 'ERROR'
            DynamoDBService.actualizar_estado_imagen(producto_id, estado_final)
        
        # Cambiar a PUBLICADO si todo es OK
        if estado_final == 'LISTA':
            RDSDatabase.actualizar_estado_producto(producto_id, 'PUBLICADO')
            mensaje = 'Producto publicado exitosamente'
            estado = 'PUBLICADO'
        else:
            mensaje = 'Imagen procesada pero con errores. Reintenta con POST /productos/{id}/reprocesar'
            estado = 'PENDIENTE'
        
        return jsonify({
            'success': True,
            'producto_id': producto_id,
            'estado': estado,
            'imagen_original': imagen_key,
            'estado_procesamiento': estado_final,
            'mensaje': mensaje
        }), 200
    
    except Exception as e:
        logger.error(f"Error en POST /productos/<id>/imagen: {e}")
        return jsonify({'error': 'Error interno del servidor', 'detalle': str(e)}), 502


# ============================================================================
# ENDPOINT 4: POST /productos/{id}/reprocesar
# Reintenta procesar la imagen guardada
# Retorna: 200 si exitoso
#          409 si no existe original
#          404 si producto no existe
# ============================================================================
@app.route('/productos/<int:producto_id>/reprocesar', methods=['POST'])
def reprocesar_imagen(producto_id):
    """POST /productos/{id}/reprocesar - Reintenta procesar imagen guardada"""
    try:
        # Validar producto
        producto = RDSDatabase.obtener_producto(producto_id)
        if not producto:
            return jsonify({'error': 'Producto no encontrado'}), 404
        
        # Obtener atributos
        atributos = DynamoDBService.obtener_atributos(producto_id)
        if not atributos:
            return jsonify({'error': 'Producto no registrado correctamente'}), 404
        
        # Validar que existe original
        imagen_original_key = atributos.get('imagen_original_key')
        if not imagen_original_key:
            return jsonify({
                'error': 'No existe imagen original',
                'detalle': 'Debe subir una imagen antes de reprocesar'
            }), 409
        
        # Actualizar estado
        DynamoDBService.actualizar_estado_imagen(producto_id, 'PROCESANDO')
        
        # Invocar Lambda nuevamente
        respuesta_lambda = LambdaService.invocar_procesar_imagen(producto_id, imagen_original_key)
        
        # Procesar respuesta
        estado_final = 'PENDIENTE'
        
        try:
            if isinstance(respuesta_lambda, dict):
                status_lambda = respuesta_lambda.get('statusCode', 500)
                body = respuesta_lambda.get('body', {})
                
                if isinstance(body, str):
                    body = eval(body) if body.startswith('{') else {}
                
                if status_lambda == 200:
                    miniatura_key = body.get('miniatura_key')
                    estado_final = body.get('estado', 'LISTA')
                    
                    if miniatura_key:
                        DynamoDBService.actualizar_estado_imagen(
                            producto_id,
                            estado_final,
                            miniatura_key=miniatura_key
                        )
                else:
                    estado_final = 'ERROR'
                    DynamoDBService.actualizar_estado_imagen(producto_id, estado_final)
        except Exception as e:
            logger.warning(f"Error procesando respuesta Lambda: {e}")
            estado_final = 'ERROR'
            DynamoDBService.actualizar_estado_imagen(producto_id, estado_final)
        
        # Cambiar estado en RDS
        if estado_final == 'LISTA':
            RDSDatabase.actualizar_estado_producto(producto_id, 'PUBLICADO')
            estado_rds = 'PUBLICADO'
        else:
            estado_rds = 'PENDIENTE'
        
        return jsonify({
            'success': True,
            'producto_id': producto_id,
            'estado_rds': estado_rds,
            'estado_procesamiento': estado_final,
            'mensaje': 'Imagen reprocesada'
        }), 200
    
    except Exception as e:
        logger.error(f"Error en POST /productos/<id>/reprocesar: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 502


# ============================================================================
# ENDPOINT 5: GET /productos
# Retorna: 200 con lista de productos PUBLICADOS con atributos y miniatura
# ============================================================================
@app.route('/productos', methods=['GET'])
def listar_productos():
    """GET /productos - Lista solo productos PUBLICADOS"""
    try:
        productos = RDSDatabase.obtener_productos_publicados()
        
        # Enriquecer con datos de DynamoDB
        productos_enriquecidos = []
        for prod in productos:
            atributos = DynamoDBService.obtener_atributos(prod['producto_id'])
            
            prod_completo = {
                'producto_id': prod['producto_id'],
                'codigo': prod['codigo'],
                'nombre': prod['nombre'],
                'precio': float(prod['precio']),
                'categoria': prod['categoria_nombre'],
                'estado': prod['estado'],
                'atributos': atributos.get('atributos', {}) if atributos else {},
                'miniatura_disponible': atributos.get('miniatura_key') is not None if atributos else False,
                'miniatura_url': f'/productos/{prod["producto_id"]}/imagen' if atributos and atributos.get('miniatura_key') else None
            }
            productos_enriquecidos.append(prod_completo)
        
        return jsonify({
            'success': True,
            'data': productos_enriquecidos,
            'count': len(productos_enriquecidos)
        }), 200
    
    except Exception as e:
        logger.error(f"Error en GET /productos: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 502


# ============================================================================
# ENDPOINT 6: GET /productos/{id}
# Retorna: 200 con detalle del producto
#          404 si no existe
# ============================================================================
@app.route('/productos/<int:producto_id>', methods=['GET'])
def obtener_producto(producto_id):
    """GET /productos/{id} - Obtiene detalle de un producto"""
    try:
        producto = RDSDatabase.obtener_producto(producto_id)
        
        if not producto:
            return jsonify({'error': 'Producto no encontrado'}), 404
        
        # Obtener atributos
        atributos = DynamoDBService.obtener_atributos(producto_id)
        
        return jsonify({
            'success': True,
            'data': {
                'producto_id': producto['producto_id'],
                'codigo': producto['codigo'],
                'nombre': producto['nombre'],
                'descripcion': producto['descripcion'],
                'precio': float(producto['precio']),
                'categoria': producto['categoria_nombre'],
                'estado': producto['estado'],
                'fecha': str(producto['fecha_creacion']),
                'atributos': atributos.get('atributos', {}) if atributos else {},
                'estado_imagen': atributos.get('estado_imagen') if atributos else 'NO_REGISTRADA',
                'miniatura_disponible': atributos.get('miniatura_key') is not None if atributos else False
            }
        }), 200
    
    except Exception as e:
        logger.error(f"Error en GET /productos/<id>: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 502


# ============================================================================
# ENDPOINT 7: GET /productos/{id}/imagen
# Retorna: 200 con bytes de la miniatura
#          404 si no existe
# ============================================================================
@app.route('/productos/<int:producto_id>/imagen', methods=['GET'])
def obtener_imagen(producto_id):
    """GET /productos/{id}/imagen - Obtiene miniatura desde S3"""
    try:
        imagen_bytes, content_type = S3Service.obtener_miniatura(producto_id)
        
        if imagen_bytes is None:
            return jsonify({'error': 'Miniatura no disponible'}), 404
        
        return send_file(
            BytesIO(imagen_bytes),
            mimetype=content_type,
            as_attachment=False,
            download_name=f'miniatura_{producto_id}.jpg'
        ), 200
    
    except Exception as e:
        logger.error(f"Error en GET /productos/<id>/imagen: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 502


# ============================================================================
# HEALTH CHECK
# ============================================================================
@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'OK', 'service': 'lomax-backend'}), 200


# ============================================================================
# ERROR HANDLERS
# ============================================================================
@app.errorhandler(400)
def bad_request(e):
    return jsonify({'error': 'Solicitud inválida'}), 400

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Recurso no encontrado'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Error interno del servidor'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
