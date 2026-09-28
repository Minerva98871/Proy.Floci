#!/usr/bin/env python3
"""
Script para probar todos los endpoints de la API
Ejecutar después de que el backend esté corriendo
"""

import requests
import json
import sys
from pathlib import Path

BASE_URL = "http://localhost:5000"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def print_test(titulo):
    print(f"\n{Colors.BLUE}{'='*70}")
    print(f"TEST: {titulo}")
    print(f"{'='*70}{Colors.RESET}")

def print_success(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.RESET}")

def print_error(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.RESET}")

def print_info(msg):
    print(f"{Colors.YELLOW}ℹ {msg}{Colors.RESET}")

# ============================================================================
# TEST 1: GET /categorias
# ============================================================================
def test_get_categorias():
    print_test("GET /categorias")
    try:
        response = requests.get(f"{BASE_URL}/categorias")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Categorías encontradas: {data['count']}")
            for cat in data['data']:
                print(f"  - {cat['nombre']} (ID: {cat['categoria_id']})")
            print_success("GET /categorias OK")
            return data['data']
        else:
            print_error(f"Error: {response.text}")
            return []
    except Exception as e:
        print_error(f"Excepción: {e}")
        return []


# ============================================================================
# TEST 2: POST /productos
# ============================================================================
def test_post_productos(categorias):
    print_test("POST /productos")
    try:
        if not categorias:
            print_error("No hay categorías disponibles")
            return None
        
        categoria_id = categorias[0]['categoria_id']
        
        payload = {
            "codigo": "TEST-001",
            "nombre": "Producto de Prueba",
            "descripcion": "Este es un producto para probar la API",
            "precio": 99.99,
            "categoria_id": categoria_id,
            "atributos": {
                "conexion": "USB",
                "color": "Negro",
                "garantia": "12 meses"
            }
        }
        
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(f"{BASE_URL}/productos", json=payload)
        print(f"Status: {response.status_code}")
        
        data = response.json()
        print(f"Respuesta: {json.dumps(data, indent=2)}")
        
        if response.status_code == 201:
            print_success("Producto creado")
            return data['producto_id']
        else:
            print_error(f"Error: {data}")
            return None
    except Exception as e:
        print_error(f"Excepción: {e}")
        return None


# ============================================================================
# TEST 3: GET /productos/{id}
# ============================================================================
def test_get_producto(producto_id):
    print_test(f"GET /productos/{producto_id}")
    try:
        response = requests.get(f"{BASE_URL}/productos/{producto_id}")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Respuesta: {json.dumps(data, indent=2)}")
            print_success("Producto obtenido")
        else:
            print_error(f"Error: {response.text}")
    except Exception as e:
        print_error(f"Excepción: {e}")


# ============================================================================
# TEST 4: POST /productos/{id}/imagen
# ============================================================================
def test_post_imagen(producto_id):
    print_test(f"POST /productos/{producto_id}/imagen")
    try:
        # Buscar imagen de prueba
        imagen_path = Path("./original_112.jpg")
        
        if not imagen_path.exists():
            print_error(f"Imagen no encontrada en {imagen_path}")
            print_info("Se debe usar una imagen válida para esta prueba")
            return
        
        with open(imagen_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(f"{BASE_URL}/productos/{producto_id}/imagen", files=files)
        
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Respuesta: {json.dumps(data, indent=2)}")
        
        if response.status_code == 200:
            print_success("Imagen subida y procesada")
        else:
            print_error(f"Error: {data}")
    except Exception as e:
        print_error(f"Excepción: {e}")


# ============================================================================
# TEST 5: GET /productos/{id}/imagen
# ============================================================================
def test_get_imagen(producto_id):
    print_test(f"GET /productos/{producto_id}/imagen")
    try:
        response = requests.get(f"{BASE_URL}/productos/{producto_id}/imagen")
        print(f"Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type')}")
        print(f"Content-Length: {len(response.content)} bytes")
        
        if response.status_code == 200:
            print_success("Miniatura obtenida")
            
            # Guardar para comparar
            with open(f"miniatura_descargada_{producto_id}.jpg", 'wb') as f:
                f.write(response.content)
            print_info(f"Miniatura guardada en miniatura_descargada_{producto_id}.jpg")
        else:
            print_error(f"Error: {response.text}")
    except Exception as e:
        print_error(f"Excepción: {e}")


# ============================================================================
# TEST 6: GET /productos
# ============================================================================
def test_get_productos():
    print_test("GET /productos")
    try:
        response = requests.get(f"{BASE_URL}/productos")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Productos publicados: {data['count']}")
            for prod in data['data']:
                print(f"  - {prod['nombre']} (ID: {prod['producto_id']}, Precio: ${prod['precio']})")
            print_success("Lista de productos obtenida")
        else:
            print_error(f"Error: {response.text}")
    except Exception as e:
        print_error(f"Excepción: {e}")


# ============================================================================
# TEST 7: POST /productos/{id}/reprocesar
# ============================================================================
def test_reprocesar_imagen(producto_id):
    print_test(f"POST /productos/{producto_id}/reprocesar")
    try:
        response = requests.post(f"{BASE_URL}/productos/{producto_id}/reprocesar")
        print(f"Status: {response.status_code}")
        
        data = response.json()
        print(f"Respuesta: {json.dumps(data, indent=2)}")
        
        if response.status_code == 200:
            print_success("Imagen reprocesada")
        else:
            print_error(f"Error: {data}")
    except Exception as e:
        print_error(f"Excepción: {e}")


# ============================================================================
# TEST 8: Errores esperados
# ============================================================================
def test_errores():
    print_test("Validación de errores")
    
    # 400: Datos inválidos
    print_info("Probando 400 - Datos inválidos...")
    response = requests.post(f"{BASE_URL}/productos", json={})
    if response.status_code == 400:
        print_success("400 obtenido correctamente")
    else:
        print_error(f"Se esperaba 400, se obtuvo {response.status_code}")
    
    # 409: Código duplicado
    print_info("Probando 409 - Código duplicado...")
    payload = {
        "codigo": "TEST-001",
        "nombre": "Prueba",
        "descripcion": "Prueba",
        "precio": 50,
        "categoria_id": 1,
        "atributos": {}
    }
    response = requests.post(f"{BASE_URL}/productos", json=payload)
    if response.status_code == 409:
        print_success("409 obtenido correctamente")
    else:
        print_error(f"Se esperaba 409, se obtuvo {response.status_code}")
    
    # 404: Producto no existe
    print_info("Probando 404 - Producto no existe...")
    response = requests.get(f"{BASE_URL}/productos/99999")
    if response.status_code == 404:
        print_success("404 obtenido correctamente")
    else:
        print_error(f"Se esperaba 404, se obtuvo {response.status_code}")


# ============================================================================
# TEST 9: Health Check
# ============================================================================
def test_health():
    print_test("Health Check")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            print_success("API disponible")
        else:
            print_error("API no disponible")
    except Exception as e:
        print_error(f"Excepción: {e}")


# ============================================================================
# MAIN
# ============================================================================
def main():
    print(f"{Colors.BLUE}┌{'─'*68}┐")
    print(f"│ TESTING ETAPA 4 - BACKEND API LOMAX                            │")
    print(f"└{'─'*68}┘{Colors.RESET}")
    
    # Test básico
    test_health()
    
    # Test categorías
    categorias = test_get_categorias()
    
    # Test crear producto
    producto_id = test_post_productos(categorias)
    
    if producto_id:
        # Test obtener producto
        test_get_producto(producto_id)
        
        # Test subir imagen
        test_post_imagen(producto_id)
        
        # Test obtener imagen
        test_get_imagen(producto_id)
        
        # Test reprocesar
        test_reprocesar_imagen(producto_id)
    
    # Test lista de productos
    test_get_productos()
    
    # Test errores
    test_errores()
    
    print(f"\n{Colors.BLUE}{'='*70}")
    print(f"TESTING COMPLETADO")
    print(f"{'='*70}{Colors.RESET}")


if __name__ == '__main__':
    main()
