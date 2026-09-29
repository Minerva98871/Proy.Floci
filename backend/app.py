import logging
import os
from io import BytesIO

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

from config import Config
from database import RDSDatabase
from dynamodb_service import (
    ESTADO_ERROR,
    ESTADO_LISTA,
    ESTADO_PROCESANDO,
    DynamoDBService,
)
from lambda_service import LambdaService
from s3_service import S3Service

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear app Flask
app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

CONTENT_TYPES = {
    'jpeg': 'image/jpeg',
    'jpg': 'image/jpeg',
    'png': 'image/png',
}


# ============================================================================
# HELPERS
# ============================================================================
def _procesar_imagen(producto_id, imagen_original_key):
    """
    Invoca Lambda de forma síncrona y sincroniza DynamoDB y RDS con el resultado.

    Devuelve (estado_final, detalle_error). estado_final vale 'LISTA' solo si la
    miniatura quedó guardada y registrada en DynamoDB.
    """
    respuesta = LambdaService.invocar_procesar_imagen(producto_id, imagen_original_key)

    if not isinstance(respuesta, dict):
        respuesta = {'estado': ESTADO_ERROR, 'error': 'Respuesta de Lambda con formato inesperado'}

    estado_final = respuesta.get('estado', ESTADO_ERROR)
    detalle_error = respuesta.get('error')

    if estado_final == ESTADO_LISTA and respuesta.get('miniatura_key'):
        DynamoDBService.actualizar_estado_imagen(
            producto_id,
            ESTADO_LISTA,
            imagen_original_key=imagen_original_key,
            miniatura_key=respuesta['miniatura_key']
        )
    else:
        # La Lambda puede haber fallado antes de escribir en DynamoDB
        # (p. ej. evento invalido), asi que el estado se corrige aqui y se
        # limpia cualquier miniatura de una carga anterior.
        DynamoDBService.actualizar_estado_imagen(
            producto_id,
            ESTADO_ERROR,
            imagen_original_key=imagen_original_key,
            imagen_error=detalle_error or 'La Lambda no genero la miniatura'
        )
        estado_final = ESTADO_ERROR

    # Solo un producto con miniatura registrada pasa a PUBLICADO en RDS
    if estado_final == ESTADO_LISTA:
        RDSDatabase.actualizar_estado_producto(producto_id, 'PUBLICADO')

    return estado_final, detalle_error


def _enriquecer(producto, incluir_descripcion=False):
    """Agrega a un producto de RDS los atributos y el estado de imagen de DynamoDB"""
    atributos = DynamoDBService.obtener_atributos(producto['producto_id']) or {}
    miniatura_key = atributos.get('miniatura_key')

    producto = dict(producto)
    producto['precio'] = float(producto['precio'])
    producto['categoria'] = producto.get('categoria_nombre')
    producto.pop('categoria_nombre', None)
    producto['atributos'] = atributos.get('atributos', {})
    producto['estado_imagen'] = atributos.get('imagen_estado', 'NO_REGISTRADA')
    producto['miniatura_disponible'] = miniatura_key is not None
    producto['miniatura_url'] = (
        f"/productos/{producto['producto_id']}/imagen" if miniatura_key else None
    )

    if not incluir_descripcion:
        producto.pop('descripcion', None)
        producto.pop('categoria_id', None)
        producto.pop('fecha_creacion', None)

    return producto


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
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({
                'error': 'Datos inválidos',
                'detalle': 'El cuerpo debe ser un objeto JSON'
            }), 400

        # Validar datos requeridos
        campos_requeridos = ['codigo', 'nombre', 'descripcion', 'precio', 'categoria_id', 'atributos']
        faltantes = [campo for campo in campos_requeridos if campo not in data]
        if faltantes:
            return jsonify({
                'error': 'Datos inválidos',
                'detalle': 'Faltan campos requeridos: ' + ', '.join(faltantes)
            }), 400

        if not isinstance(data['atributos'], dict):
            return jsonify({
                'error': 'Datos inválidos',
                'detalle': 'El campo atributos debe ser un objeto'
            }), 400

        codigo = data['codigo']
        nombre = data['nombre']
        descripcion = data['descripcion']
        if not all(isinstance(v, str) for v in (codigo, nombre, descripcion)):
            return jsonify({
                'error': 'Datos inválidos',
                'detalle': 'codigo, nombre y descripcion deben ser texto'
            }), 400

        codigo = codigo.strip()
        nombre = nombre.strip()
        descripcion = descripcion.strip()

        try:
            precio = float(data['precio'])
            categoria_id = int(data['categoria_id'])
        except (TypeError, ValueError):
            return jsonify({
                'error': 'Datos inválidos',
                'detalle': 'precio y categoria_id deben ser numéricos'
            }), 400

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
            elif error == "Datos inválidos":
                return jsonify({'error': error}), 400
            return jsonify({'error': error}), 502

        # Guardar atributos en DynamoDB
        if not DynamoDBService.guardar_atributos(producto_id, codigo, data['atributos']):
            # Sin item en DynamoDB el producto quedaria huerfano: se revierte.
            logger.error(f"Fallo al guardar atributos para producto {producto_id}, revirtiendo RDS")
            RDSDatabase.eliminar_producto(producto_id)
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

        if tamaño == 0:
            return jsonify({'error': 'Archivo vacío'}), 400

        if tamaño > Config.MAX_IMAGE_SIZE:
            return jsonify({
                'error': 'Archivo muy grande',
                'detalle': f'Máximo {Config.MAX_IMAGE_SIZE / 1024 / 1024:.0f} MiB'
            }), 413

        # Validar formato por extension. La Lambda vuelve a validar el
        # contenido real de la imagen, asi que esto es solo un filtro previo.
        extension = archivo.filename.rsplit('.', 1)[-1].lower() if '.' in archivo.filename else ''
        if extension not in Config.ALLOWED_IMAGE_FORMATS:
            return jsonify({
                'error': 'Formato no permitido',
                'detalle': f'Permitidos: {", ".join(sorted(Config.ALLOWED_IMAGE_FORMATS))}'
            }), 415

        # Leer contenido
        imagen_bytes = archivo.read()

        # Guardar original en S3
        imagen_key = S3Service.guardar_original(
            producto_id, imagen_bytes, archivo.filename, CONTENT_TYPES[extension]
        )

        if not imagen_key:
            return jsonify({'error': 'Error guardando imagen en S3'}), 503

        # Marcar PROCESANDO. La Lambda confirmara LISTA o ERROR.
        DynamoDBService.actualizar_estado_imagen(
            producto_id,
            ESTADO_PROCESANDO,
            imagen_original_key=imagen_key
        )

        estado_final, detalle_error = _procesar_imagen(producto_id, imagen_key)

        if estado_final == ESTADO_LISTA:
            return jsonify({
                'success': True,
                'producto_id': producto_id,
                'estado': 'PUBLICADO',
                'imagen_original': imagen_key,
                'estado_procesamiento': estado_final,
                'mensaje': 'Producto publicado exitosamente'
            }), 200

        return jsonify({
            'success': False,
            'producto_id': producto_id,
            'estado': 'PENDIENTE',
            'imagen_original': imagen_key,
            'estado_procesamiento': estado_final,
            'detalle': detalle_error,
            'mensaje': 'La imagen no se pudo procesar. Reintenta con POST '
                       f'/productos/{producto_id}/reprocesar'
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

        # Marcar PROCESANDO antes de invocar
        DynamoDBService.actualizar_estado_imagen(producto_id, ESTADO_PROCESANDO)

        estado_final, detalle_error = _procesar_imagen(producto_id, imagen_original_key)

        return jsonify({
            'success': estado_final == ESTADO_LISTA,
            'producto_id': producto_id,
            'estado_rds': 'PUBLICADO' if estado_final == ESTADO_LISTA else 'PENDIENTE',
            'estado_procesamiento': estado_final,
            'detalle': detalle_error,
            'mensaje': 'Imagen reprocesada' if estado_final == ESTADO_LISTA
                       else 'La imagen no se pudo procesar'
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
        if productos is None:
            return jsonify({'error': 'Fallo al consultar productos'}), 502

        productos_enriquecidos = [_enriquecer(prod) for prod in productos]

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

        producto = _enriquecer(producto, incluir_descripcion=True)
        producto['fecha'] = str(producto.pop('fecha_creacion'))

        return jsonify({
            'success': True,
            'data': producto
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
        atributos = DynamoDBService.obtener_atributos(producto_id)
        if not atributos:
            return jsonify({'error': 'Producto no encontrado'}), 404

        # La clave la calcula lambda/handler.py, hay que leerla de DynamoDB
        miniatura_key = atributos.get('miniatura_key')
        if not miniatura_key:
            return jsonify({
                'error': 'Miniatura no disponible',
                'detalle': f"Estado del procesamiento: {atributos.get('imagen_estado', 'NO_REGISTRADA')}"
            }), 404

        imagen_bytes, content_type = S3Service.obtener_miniatura(miniatura_key)

        if imagen_bytes is None:
            return jsonify({'error': 'Miniatura no disponible'}), 404

        return send_file(
            BytesIO(imagen_bytes),
            mimetype=content_type or 'image/jpeg',
            as_attachment=False,
            download_name=f'miniatura_{producto_id}.jpg'
        )

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
    app.run(host='0.0.0.0', port=5000, debug=Config.DEBUG)
