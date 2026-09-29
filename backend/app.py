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

# Pasos del flujo de alta de un producto. Se devuelven en el campo
# paso_fallido de cada error para poder localizar donde se rompio la cadena.
PASO_VALIDACION = 'validacion'
PASO_RDS = 'rds'
PASO_DYNAMODB = 'dynamodb'
PASO_S3_ORIGINAL = 's3_original'
PASO_S3_MINIATURA = 's3_miniatura'
PASO_LAMBDA = 'lambda'
PASO_LECTURA = 'lectura'


# ============================================================================
# HELPERS
# ============================================================================
def _error(mensaje, status, paso, detalle=None, extra=None):
    """
    Sobre de error uniforme.

    paso_fallido identifica la etapa del flujo que fallo, de modo que un 502
    de la API se pueda atribuir a RDS, DynamoDB, S3 o Lambda sin tener que
    leer los logs.
    """
    cuerpo = {'error': mensaje, 'paso_fallido': paso}
    if detalle:
        cuerpo['detalle'] = detalle
    if extra:
        cuerpo.update(extra)
    return jsonify(cuerpo), status


def _procesar_imagen(producto_id, imagen_original_key):
    """
    Invoca Lambda de forma síncrona y sincroniza DynamoDB y RDS con el resultado.

    Devuelve (estado_final, detalle_error). estado_final vale 'LISTA' solo si la
    miniatura quedó guardada y registrada en DynamoDB.
    """
    respuesta = LambdaService.invocar_procesar_imagen(producto_id, imagen_original_key)

    if not isinstance(respuesta, dict):
        respuesta = {
            'estado': ESTADO_ERROR,
            'error': 'Respuesta de Lambda con formato inesperado',
        }

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
    # Indica si hay original guardado, que es lo que permite reintentar el
    # procesamiento sin volver a subir la imagen.
    producto['imagen_original_disponible'] = bool(atributos.get('imagen_original_key'))
    if atributos.get('imagen_error'):
        producto['imagen_error'] = atributos['imagen_error']

    if not incluir_descripcion:
        producto.pop('descripcion', None)
        producto.pop('categoria_id', None)
        producto.pop('fecha_creacion', None)

    return producto


def _validar_imagen(archivo):
    """
    Valida tamano y extension de la imagen subida.

    Devuelve (ok, status, mensaje, paso, detalle, bytes, extension).
    La Lambda vuelve a validar el contenido real, asi que la extension es
    un filtro previo barato, no la garantia final.
    """
    if 'file' not in request.files:
        return False, 400, 'No se envió archivo', PASO_VALIDACION, None, None, None

    if archivo.filename == '':
        return False, 400, 'Archivo vacío', PASO_VALIDACION, None, None, None

    archivo.seek(0, os.SEEK_END)
    tamano = archivo.tell()
    archivo.seek(0)

    if tamano == 0:
        return False, 400, 'Archivo vacío', PASO_VALIDACION, None, None, None

    if tamano > Config.MAX_IMAGE_SIZE:
        return (False, 413, 'Archivo muy grande', PASO_VALIDACION,
                f'Máximo {Config.MAX_IMAGE_SIZE / 1024 / 1024:.0f} MiB', None, None)

    extension = archivo.filename.rsplit('.', 1)[-1].lower() if '.' in archivo.filename else ''
    if extension not in Config.ALLOWED_IMAGE_FORMATS:
        return (False, 415, 'Formato no permitido', PASO_VALIDACION,
                f'Permitidos: {", ".join(sorted(Config.ALLOWED_IMAGE_FORMATS))}', None, None)

    return True, 200, None, None, None, archivo.read(), extension


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
        return jsonify({
            'error': categorias.get('error', 'Fallo al consultar categorías'),
            'paso_fallido': PASO_RDS,
            'detalle': categorias.get('details')
        }), status_code
    except Exception as e:
        logger.error(f"Error en GET /categorias: {e}")
        return _error('Error interno del servidor', 502, PASO_RDS, str(e))


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
            return _error('Datos inválidos', 400, PASO_VALIDACION,
                          'El cuerpo debe ser un objeto JSON')

        # Validar datos requeridos
        campos_requeridos = ['codigo', 'nombre', 'descripcion', 'precio', 'categoria_id', 'atributos']
        faltantes = [campo for campo in campos_requeridos if campo not in data]
        if faltantes:
            return _error('Datos inválidos', 400, PASO_VALIDACION,
                          'Faltan campos requeridos: ' + ', '.join(faltantes))

        if not isinstance(data['atributos'], dict):
            return _error('Datos inválidos', 400, PASO_VALIDACION,
                          'El campo atributos debe ser un objeto')

        codigo = data['codigo']
        nombre = data['nombre']
        descripcion = data['descripcion']
        if not all(isinstance(v, str) for v in (codigo, nombre, descripcion)):
            return _error('Datos inválidos', 400, PASO_VALIDACION,
                          'codigo, nombre y descripcion deben ser texto')

        codigo = codigo.strip()
        nombre = nombre.strip()
        descripcion = descripcion.strip()

        try:
            precio = float(data['precio'])
            categoria_id = int(data['categoria_id'])
        except (TypeError, ValueError):
            return _error('Datos inválidos', 400, PASO_VALIDACION,
                          'precio y categoria_id deben ser numéricos')

        if not codigo or not nombre or not descripcion:
            return _error('Datos inválidos', 400, PASO_VALIDACION, 'Campos vacíos')

        if precio < 0:
            return _error('Datos inválidos', 400, PASO_VALIDACION,
                          'Precio no puede ser negativo')

        if categoria_id <= 0:
            return _error('Datos inválidos', 400, PASO_VALIDACION, 'Categoría no válida')

        # Paso RDS
        producto_id, error = RDSDatabase.crear_producto(codigo, nombre, descripcion, precio, categoria_id)

        if error:
            if error == "Código duplicado":
                return _error(error, 409, PASO_RDS, 'El índice UNIQUE de codigo ya tiene ese valor')
            if error == "Categoría no existe":
                return _error(error, 400, PASO_RDS, 'La FK categoria_id no tiene coincidencia')
            if error == "Datos inválidos":
                return _error(error, 400, PASO_RDS)
            return _error('Fallo al crear el producto en RDS', 502, PASO_RDS, error)

        # Paso DynamoDB
        if not DynamoDBService.guardar_atributos(producto_id, codigo, data['atributos']):
            # Sin item en DynamoDB el producto quedaria huerfano: se revierte.
            logger.error(f"Fallo al guardar atributos para producto {producto_id}, revirtiendo RDS")
            RDSDatabase.eliminar_producto(producto_id)
            return _error('Fallo al guardar atributos', 502, PASO_DYNAMODB,
                          'No se pudieron guardar los atributos en DynamoDB; '
                          'se revirtio la fila de RDS')

        return jsonify({
            'success': True,
            'producto_id': producto_id,
            'codigo': codigo,
            'nombre': nombre,
            'estado': 'PENDIENTE',
            'siguiente_paso': 'POST /productos/{id}/imagen para completar y publicar',
            'mensaje': 'Producto creado. Carga la imagen para publicarlo.'
        }), 201

    except Exception as e:
        logger.error(f"Error en POST /productos: {e}")
        return _error('Error interno del servidor', 502, PASO_VALIDACION, str(e))


# ============================================================================
# ENDPOINT 3: POST /productos/{id}/imagen
# Recibe: imagen JPEG o PNG
# Retorna: 200 con PUBLICADO si todo OK
#          413 si mayor a 5 MiB
#          415 si formato no permitido
#          404 si producto no existe
#          502/503 si falla un servicio
# ============================================================================
@app.route('/productos/<int:producto_id>/imagen', methods=['POST'])
def subir_imagen(producto_id):
    """POST /productos/{id}/imagen - Sube imagen y procesa con Lambda"""
    try:
        producto = RDSDatabase.obtener_producto(producto_id)
        if not producto:
            return _error('Producto no encontrado', 404, PASO_RDS)

        if not DynamoDBService.existe_item(producto_id):
            return _error('Producto no completamente registrado', 404, PASO_DYNAMODB,
                          'No existe el item de atributos para este producto_id')

        ok, status, mensaje, paso, detalle, imagen_bytes, extension = _validar_imagen(
            request.files['file']
        )
        if not ok:
            return _error(mensaje, status, paso, detalle)

        # Paso S3: guardar el original
        imagen_key = S3Service.guardar_original(
            producto_id, imagen_bytes, request.files['file'].filename,
            CONTENT_TYPES[extension]
        )
        if not imagen_key:
            return _error('Error guardando imagen en S3', 503, PASO_S3_ORIGINAL,
                          'No se pudo escribir en el bucket de originales')

        DynamoDBService.actualizar_estado_imagen(
            producto_id, ESTADO_PROCESANDO, imagen_original_key=imagen_key
        )

        # Paso Lambda
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

        # El producto sigue PENDIENTE para poder reintentar.
        return _error('La imagen no se pudo procesar', 200, PASO_LAMBDA, detalle_error, extra={
            'success': False,
            'producto_id': producto_id,
            'estado': 'PENDIENTE',
            'imagen_original': imagen_key,
            'estado_procesamiento': estado_final,
            'reintentable': True,
            'siguiente_paso': f'POST /productos/{producto_id}/reprocesar'
        })

    except Exception as e:
        logger.error(f"Error en POST /productos/<id>/imagen: {e}")
        return _error('Error interno del servidor', 502, PASO_S3_ORIGINAL, str(e))


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
        producto = RDSDatabase.obtener_producto(producto_id)
        if not producto:
            return _error('Producto no encontrado', 404, PASO_RDS)

        atributos = DynamoDBService.obtener_atributos(producto_id)
        if not atributos:
            return _error('Producto no registrado correctamente', 404, PASO_DYNAMODB)

        imagen_original_key = atributos.get('imagen_original_key')
        if not imagen_original_key:
            return _error('No existe imagen original', 409, PASO_S3_ORIGINAL,
                          'Debe subir una imagen antes de reprocesar')

        DynamoDBService.actualizar_estado_imagen(producto_id, ESTADO_PROCESANDO)

        estado_final, detalle_error = _procesar_imagen(producto_id, imagen_original_key)

        if estado_final == ESTADO_LISTA:
            return jsonify({
                'success': True,
                'producto_id': producto_id,
                'estado_rds': 'PUBLICADO',
                'estado_procesamiento': estado_final,
                'detalle': None,
                'mensaje': 'Imagen reprocesada'
            }), 200

        return _error('La imagen no se pudo procesar', 200, PASO_LAMBDA, detalle_error, extra={
            'success': False,
            'producto_id': producto_id,
            'estado_rds': 'PENDIENTE',
            'estado_procesamiento': estado_final,
            'reintentable': True
        })

    except Exception as e:
        logger.error(f"Error en POST /productos/<id>/reprocesar: {e}")
        return _error('Error interno del servidor', 502, PASO_LAMBDA, str(e))


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
            return _error('Fallo al consultar productos', 502, PASO_RDS)

        productos_enriquecidos = [_enriquecer(prod) for prod in productos]

        return jsonify({
            'success': True,
            'data': productos_enriquecidos,
            'count': len(productos_enriquecidos)
        }), 200

    except Exception as e:
        logger.error(f"Error en GET /productos: {e}")
        return _error('Error interno del servidor', 502, PASO_RDS, str(e))


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
            return _error('Producto no encontrado', 404, PASO_RDS)

        producto = _enriquecer(producto, incluir_descripcion=True)
        producto['fecha'] = str(producto.pop('fecha_creacion'))
        producto['reintentable'] = (
            producto['estado'] == 'PENDIENTE' and producto['estado_imagen'] == ESTADO_ERROR
        )

        return jsonify({
            'success': True,
            'data': producto
        }), 200

    except Exception as e:
        logger.error(f"Error en GET /productos/<id>: {e}")
        return _error('Error interno del servidor', 502, PASO_RDS, str(e))


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
            return _error('Producto no encontrado', 404, PASO_DYNAMODB)

        # La clave la calcula lambda/handler.py, hay que leerla de DynamoDB
        miniatura_key = atributos.get('miniatura_key')
        if not miniatura_key:
            return _error('Miniatura no disponible', 404, PASO_S3_MINIATURA,
                          f"Estado del procesamiento: {atributos.get('imagen_estado', 'NO_REGISTRADA')}")

        imagen_bytes, content_type = S3Service.obtener_miniatura(miniatura_key)

        if imagen_bytes is None:
            return _error('Miniatura no disponible', 404, PASO_S3_MINIATURA,
                          f'La clave {miniatura_key} no existe en el bucket de miniaturas')

        return send_file(
            BytesIO(imagen_bytes),
            mimetype=content_type or 'image/jpeg',
            as_attachment=False,
            download_name=f'miniatura_{producto_id}.jpg'
        )

    except Exception as e:
        logger.error(f"Error en GET /productos/<id>/imagen: {e}")
        return _error('Error interno del servidor', 502, PASO_S3_MINIATURA, str(e))


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
    return _error('Solicitud inválida', 400, PASO_VALIDACION)


@app.errorhandler(404)
def not_found(e):
    return _error('Recurso no encontrado', 404, PASO_LECTURA)


@app.errorhandler(500)
def internal_error(e):
    return _error('Error interno del servidor', 500, PASO_LECTURA)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=Config.DEBUG)
