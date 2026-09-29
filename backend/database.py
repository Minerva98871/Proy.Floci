import logging

import mysql.connector
from mysql.connector import Error
from mysql.connector.errorcode import ER_DUP_ENTRY, ER_NO_REFERENCED_ROW_2

from config import Config

logger = logging.getLogger(__name__)


class RDSDatabase:
    """Gestor de conexiones y operaciones en RDS"""

    @staticmethod
    def get_connection():
        """Obtiene conexión a RDS"""
        try:
            conn = mysql.connector.connect(
                host=Config.RDS_HOST,
                port=Config.RDS_PORT,
                user=Config.RDS_USER,
                password=Config.RDS_PASSWORD,
                database=Config.RDS_DATABASE
            )
            return conn
        except Error as e:
            logger.error(f"Error conexión RDS: {e}")
            raise

    @staticmethod
    def get_categorias():
        """GET /categorias - Obtiene todas las categorías"""
        try:
            conn = RDSDatabase.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT categoria_id, nombre FROM Categorias ORDER BY nombre")
            categorias = cursor.fetchall()
            cursor.close()
            conn.close()
            return categorias, 200
        except Error as e:
            logger.error(f"Error obteniendo categorías: {e}")
            return {"error": "Fallo al consultar categorías", "details": str(e)}, 502

    @staticmethod
    def categoria_existe(categoria_id):
        """Verifica si una categoría existe"""
        try:
            conn = RDSDatabase.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM Categorias WHERE categoria_id = %s", (categoria_id,))
            existe = cursor.fetchone() is not None
            cursor.close()
            conn.close()
            return existe
        except Error as e:
            logger.error(f"Error verificando categoría: {e}")
            return False

    @staticmethod
    def codigo_existe(codigo):
        """Verifica si un código de producto ya existe"""
        try:
            conn = RDSDatabase.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM Productos WHERE codigo = %s", (codigo,))
            existe = cursor.fetchone() is not None
            cursor.close()
            conn.close()
            return existe
        except Error as e:
            logger.error(f"Error verificando código: {e}")
            return False

    @staticmethod
    def crear_producto(codigo, nombre, descripcion, precio, categoria_id):
        """
        POST /productos - Crea un nuevo producto en estado PENDIENTE.

        Devuelve (producto_id, None) o (None, mensaje_de_error). La unicidad del
        codigo y la FK de categoria se resuelven con las restricciones de
        MySQL/InnoDB (ver database/schema.sql); la comprobacion previa solo
        evita el viaje de ida y vuelta.
        """
        if not codigo or not nombre or precio < 0:
            return None, "Datos inválidos"

        if not RDSDatabase.categoria_existe(categoria_id):
            return None, "Categoría no existe"

        conn = None
        try:
            conn = RDSDatabase.get_connection()
            cursor = conn.cursor()

            # IMPORTANTE: Usar fecha_creacion (no fecha)
            query = """
            INSERT INTO Productos (codigo, nombre, descripcion, precio, categoria_id, estado, fecha_creacion)
            VALUES (%s, %s, %s, %s, %s, 'PENDIENTE', NOW())
            """
            cursor.execute(query, (codigo, nombre, descripcion, precio, categoria_id))
            conn.commit()

            producto_id = cursor.lastrowid
            cursor.close()
            return producto_id, None
        except Error as e:
            if conn is not None:
                conn.rollback()
            if e.errno == ER_DUP_ENTRY:
                return None, "Código duplicado"
            if e.errno == ER_NO_REFERENCED_ROW_2:
                return None, "Categoría no existe"
            logger.error(f"Error creando producto: {e}")
            return None, str(e)
        finally:
            if conn is not None and not conn.is_closed():
                conn.close()

    @staticmethod
    def obtener_producto(producto_id):
        """GET /productos/{id} - Obtiene detalle de un producto"""
        conn = None
        try:
            conn = RDSDatabase.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT p.producto_id, p.codigo, p.nombre, p.descripcion, p.precio,
                       p.categoria_id, c.nombre as categoria_nombre, p.estado, p.fecha_creacion
                FROM Productos p
                LEFT JOIN Categorias c ON p.categoria_id = c.categoria_id
                WHERE p.producto_id = %s
            """, (producto_id,))
            producto = cursor.fetchone()
            cursor.close()
            return producto
        except Error as e:
            logger.error(f"Error obteniendo producto: {e}")
            return None
        finally:
            if conn is not None and not conn.is_closed():
                conn.close()

    @staticmethod
    def obtener_productos_publicados():
        """
        GET /productos - Obtiene solo productos PUBLICADOS.

        Devuelve None si la consulta falla, para que la API responda 502 en
        lugar de un 200 con lista vacia que ocultaria la caida de RDS.
        """
        conn = None
        try:
            conn = RDSDatabase.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT p.producto_id, p.codigo, p.nombre, p.precio,
                       c.nombre as categoria_nombre, p.estado
                FROM Productos p
                LEFT JOIN Categorias c ON p.categoria_id = c.categoria_id
                WHERE p.estado = 'PUBLICADO'
                ORDER BY p.fecha_creacion DESC
            """)
            productos = cursor.fetchall()
            cursor.close()
            return productos
        except Error as e:
            logger.error(f"Error obteniendo productos: {e}")
            return None
        finally:
            if conn is not None and not conn.is_closed():
                conn.close()

    @staticmethod
    def eliminar_producto(producto_id):
        """
        Elimina un producto recien creado.

        Se usa como accion compensatoria cuando el item de DynamoDB no se pudo
        escribir: es preferible no dejar filas huerfanas en RDS que un producto
        que el endpoint POST /productos declares incompleto.
        """
        conn = None
        try:
            conn = RDSDatabase.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Productos WHERE producto_id = %s", (producto_id,))
            conn.commit()
            cursor.close()
            logger.warning(f"Producto {producto_id} revertido por fallo en DynamoDB")
            return True
        except Error as e:
            if conn is not None:
                conn.rollback()
            logger.error(f"Error revirtiendo producto {producto_id}: {e}")
            return False
        finally:
            if conn is not None and not conn.is_closed():
                conn.close()

    @staticmethod
    def actualizar_estado_producto(producto_id, estado):
        """Actualiza el estado de un producto"""
        conn = None
        try:
            conn = RDSDatabase.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE Productos SET estado = %s WHERE producto_id = %s",
                (estado, producto_id)
            )
            conn.commit()
            cursor.close()
            return True
        except Error as e:
            if conn is not None:
                conn.rollback()
            logger.error(f"Error actualizando estado: {e}")
            return False
        finally:
            if conn is not None and not conn.is_closed():
                conn.close()
