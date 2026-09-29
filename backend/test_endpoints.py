#!/usr/bin/env python3
"""
Prueba de integracion de los 7 endpoints de la API (Etapa 4).

Requiere la pila levantada (scripts/setup.ps1, scripts/stage3.ps1 y
docker compose up -d backend frontend) y una imagen valida en la raiz del
proyecto.

Uso:  python backend/test_endpoints.py
Salida: 0 si todo pasa, 1 si algun endpoint no cumple lo esperado.
"""

import json
import sys
import uuid
from pathlib import Path

import requests

BASE_URL = "http://localhost:5000"
RAIZ = Path(__file__).resolve().parent.parent
IMAGEN = RAIZ / "original_112.jpg"

resultados = []


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'


def check(nombre, condicion, detalle=""):
    resultados.append((nombre, bool(condicion)))
    if condicion:
        print(f"  {Colors.GREEN}[OK]{Colors.RESET}   {nombre}")
    else:
        print(f"  {Colors.RED}[FALLA]{Colors.RESET} {nombre}  {Colors.YELLOW}{detalle}{Colors.RESET}")


def titulo(texto):
    print(f"\n{Colors.BLUE}{'=' * 72}\n{texto}\n{'=' * 72}{Colors.RESET}")


def esperar_json(response):
    try:
        return response.json()
    except ValueError:
        return {"_cuerpo_no_json": response.text[:300]}


# ============================================================================
def test_health():
    titulo("GET /health")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=15)
    except requests.RequestException as e:
        check("backend accesible", False, str(e))
        return False
    check("responde 200", r.status_code == 200, f"status={r.status_code}")
    return r.status_code == 200


def test_categorias():
    titulo("GET /categorias")
    r = requests.get(f"{BASE_URL}/categorias", timeout=30)
    data = esperar_json(r)
    check("responde 200", r.status_code == 200, f"status={r.status_code} {data}")
    check("devuelve categorias", data.get("count", 0) > 0, json.dumps(data)[:200])
    return data.get("data", [])


def test_crear_producto(categorias):
    titulo("POST /productos")
    if not categorias:
        check("hay categorias para probar", False)
        return None

    codigo = f"TEST-{uuid.uuid4().hex[:8].upper()}"
    payload = {
        "codigo": codigo,
        "nombre": "Producto de prueba",
        "descripcion": "Producto creado por test_endpoints.py",
        "precio": 99.99,
        "categoria_id": categorias[0]["categoria_id"],
        "atributos": {"conexion": "USB", "color": "Negro"}
    }
    r = requests.post(f"{BASE_URL}/productos", json=payload, timeout=30)
    data = esperar_json(r)
    check("responde 201", r.status_code == 201, f"status={r.status_code} {data}")
    producto_id = data.get("producto_id")
    check("devuelve producto_id", producto_id is not None, json.dumps(data)[:200])
    check("estado inicial PENDIENTE", data.get("estado") == "PENDIENTE", json.dumps(data)[:200])

    # 409: el mismo codigo no puede repetirse
    r2 = requests.post(f"{BASE_URL}/productos", json=payload, timeout=30)
    check("codigo duplicado -> 409", r2.status_code == 409, f"status={r2.status_code}")

    # 400: precio negativo
    malo = dict(payload, codigo=f"{codigo}-N", precio=-1)
    r3 = requests.post(f"{BASE_URL}/productos", json=malo, timeout=30)
    check("precio negativo -> 400", r3.status_code == 400, f"status={r3.status_code}")

    # 400: categoria inexistente
    malo = dict(payload, codigo=f"{codigo}-C", categoria_id=999999)
    r4 = requests.post(f"{BASE_URL}/productos", json=malo, timeout=30)
    check("categoria inexistente -> 400", r4.status_code == 400, f"status={r4.status_code}")

    return producto_id


def test_registro_dynamodb(producto_id):
    titulo("GET /productos/{id} - registro en DynamoDB")
    r = requests.get(f"{BASE_URL}/productos/{producto_id}", timeout=30)
    data = esperar_json(r)
    check("responde 200", r.status_code == 200, f"status={r.status_code} {data}")
    if r.status_code != 200:
        return
    detalle = data.get("data", {})
    check("atributos guardados en DynamoDB", detalle.get("atributos") != {}, json.dumps(detalle)[:200])
    check("imagen_estado inicial PENDIENTE",
          detalle.get("estado_imagen") == "PENDIENTE", f"estado_imagen={detalle.get('estado_imagen')}")


def test_subir_imagen(producto_id):
    titulo(f"POST /productos/{producto_id}/imagen - procesamiento con Lambda")
    if not IMAGEN.exists():
        check("imagen de prueba disponible", False, f"falta {IMAGEN}")
        return

    with open(IMAGEN, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/productos/{producto_id}/imagen",
            files={"file": (IMAGEN.name, f, "image/jpeg")},
            timeout=180,
        )
    data = esperar_json(r)
    check("responde 200", r.status_code == 200, f"status={r.status_code} {data}")

    # Este es el punto critico: la Lambda debe devolver estado LISTA y el
    # producto debe quedar PUBLICADO en RDS.
    check("Lambda devolvio LISTA", data.get("estado_procesamiento") == "LISTA",
          f"estado={data.get('estado_procesamiento')} detalle={data.get('detalle')}")
    check("producto PUBLICADO en RDS", data.get("estado") == "PUBLICADO",
          f"estado={data.get('estado')}")
    check("original registrado", bool(data.get("imagen_original")),
          json.dumps(data)[:200])


def test_obtener_imagen(producto_id):
    titulo(f"GET /productos/{producto_id}/imagen - miniatura")
    r = requests.get(f"{BASE_URL}/productos/{producto_id}/imagen", timeout=60)
    check("responde 200", r.status_code == 200, f"status={r.status_code} {r.text[:200]}")
    if r.status_code != 200:
        return
    check("content-type JPEG", r.headers.get("Content-Type", "").startswith("image/jpeg"),
          r.headers.get("Content-Type", ""))
    check("son bytes de imagen", len(r.content) > 100, f"{len(r.content)} bytes")
    destino = RAIZ / f"miniatura_descargada_{producto_id}.jpg"
    destino.write_bytes(r.content)
    print(f"  {Colors.YELLOW}miniatura guardada en {destino.name}{Colors.RESET}")


def test_reprocesar(producto_id):
    titulo(f"POST /productos/{producto_id}/reprocesar")
    r = requests.post(f"{BASE_URL}/productos/{producto_id}/reprocesar", timeout=180)
    data = esperar_json(r)
    check("responde 200", r.status_code == 200, f"status={r.status_code} {data}")
    check("reproceso deja la imagen LISTA", data.get("estado_procesamiento") == "LISTA",
          f"estado={data.get('estado_procesamiento')} detalle={data.get('detalle')}")
    check("producto sigue PUBLICADO", data.get("estado_rds") == "PUBLICADO",
          f"estado_rds={data.get('estado_rds')}")


def test_lista_publicados():
    titulo("GET /productos - solo publicados")
    r = requests.get(f"{BASE_URL}/productos", timeout=60)
    data = esperar_json(r)
    check("responde 200", r.status_code == 200, f"status={r.status_code} {data}")
    if r.status_code != 200:
        return
    check("hay al menos un publicado", data.get("count", 0) > 0, "lista vacia")
    check("ninguno en PENDIENTE",
          all(p.get("estado") == "PUBLICADO" for p in data.get("data", [])),
          "aparecen productos no publicados")


def test_404():
    titulo("Errores")
    r = requests.get(f"{BASE_URL}/productos/999999", timeout=30)
    check("producto inexistente -> 404", r.status_code == 404, f"status={r.status_code}")

    r = requests.post(f"{BASE_URL}/productos", json={}, timeout=30)
    check("payload vacio -> 400", r.status_code == 400, f"status={r.status_code}")

    r = requests.post(f"{BASE_URL}/productos/999999/reprocesar", timeout=30)
    check("reprocesar inexistente -> 404", r.status_code == 404, f"status={r.status_code}")


def main():
    print(f"{Colors.BLUE}{'=' * 72}")
    print("ETAPA 4 - PRUEBA DE INTEGRACION DE LA API LOMAX")
    print(f"{'=' * 72}{Colors.RESET}")

    if not test_health():
        print(f"\n{Colors.RED}El backend no responde en {BASE_URL}. "
              f"Levantalo con: docker compose up -d backend{Colors.RESET}")
        return 1

    categorias = test_categorias()
    producto_id = test_crear_producto(categorias)

    if producto_id:
        test_registro_dynamodb(producto_id)
        test_subir_imagen(producto_id)
        test_obtener_imagen(producto_id)
        test_reprocesar(producto_id)

    test_lista_publicados()
    test_404()

    ok = sum(1 for _, p in resultados if p)
    total = len(resultados)
    print(f"\n{Colors.BLUE}{'=' * 72}")
    color = Colors.GREEN if ok == total else Colors.RED
    print(f"{color}RESULTADO: {ok}/{total} comprobaciones OK{Colors.RESET}")
    if ok != total:
        for nombre, paso in resultados:
            if not paso:
                print(f"  {Colors.RED}- {nombre}{Colors.RESET}")
    print(f"{'=' * 72}{Colors.RESET}")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
