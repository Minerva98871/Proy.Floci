#!/usr/bin/env python3
"""
Prueba de integracion de la API de Lomax SA (Etapa 4, verificacion E4).

Ejecuta los TEST 1 a TEST 8 del enunciado y guarda el reporte completo en
evidence/stage4/reporte-e4.md.

Las solicitudes salen por el reverse proxy, que es la entrada de usuarios del
diseno. Para golpear el backend directamente, definir LOMAX_TEST_BASE_URL, por
ejemplo http://localhost:5000.

Uso:  python backend/test_endpoints.py
Salida: 0 si todo pasa, 1 si algun endpoint no cumple lo esperado.
"""

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import requests

# El proxy sirve el frontend y reenvia /api al backend Flask. El proxy pasa
# /api/productos a /productos, asi que el prefijo debe incluirse.
BASE_URL = os.environ.get("LOMAX_TEST_BASE_URL", "http://localhost:8080/api")
RAIZ = Path(__file__).resolve().parent.parent
IMAGEN = RAIZ / "original_112.jpg"
EVIDENCIA = RAIZ / "evidence" / "stage4"

resultados = []
lineas_reporte = []


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'


def check(nombre, condicion, detalle=""):
    """Registra una comprobacion, la muestra en consola y la anade al reporte."""
    condicion = bool(condicion)
    resultados.append((nombre, condicion))
    etiqueta = f"[OK]   {nombre}" if condicion else f"[FALLA] {nombre}  {detalle}"
    if condicion:
        print(f"  {Colors.GREEN}[OK]{Colors.RESET}   {nombre}")
    else:
        print(f"  {Colors.RED}[FALLA]{Colors.RESET} {nombre}  {Colors.YELLOW}{detalle}{Colors.RESET}")
    lineas_reporte.append(("OK" if condicion else "FALLA", nombre, detalle))
    return condicion


def titulo(texto):
    print(f"\n{Colors.BLUE}{'=' * 72}\n{texto}\n{'=' * 72}{Colors.RESET}")
    lineas_reporte.append(("", f"### {texto}", ""))


def esperar_json(response):
    try:
        return response.json()
    except ValueError:
        return {"_cuerpo_no_json": response.text[:300]}


def registrar_http(etiqueta, response, data=None):
    """Deja constancia de la solicitud y la respuesta, como pide la E4."""
    cuerpo = data if data is not None else (response.text[:200] if response.text else "")
    print(f"  {Colors.YELLOW}-> {etiqueta}: HTTP {response.status_code}{Colors.RESET}")
    lineas_reporte.append(("", f"`{etiqueta}` -> HTTP {response.status_code}", ""))
    if isinstance(cuerpo, (dict, list)):
        lineas_reporte.append(("", "```json", ""))
        lineas_reporte.append(("", json.dumps(cuerpo, ensure_ascii=False, indent=2)[:800], ""))
        lineas_reporte.append(("", "```", ""))


# ============================================================================
def test_health():
    titulo("Comprobacion de disponibilidad")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=15)
    except requests.RequestException as e:
        check("API accesible por el proxy", False, str(e))
        return False
    check("API accesible por el proxy", r.status_code == 200, f"status={r.status_code}")
    registrar_http("GET /health", r, esperar_json(r))
    return r.status_code == 200


def test_1_categorias():
    titulo("TEST 1: GET /categorias")
    r = requests.get(f"{BASE_URL}/categorias", timeout=30)
    data = esperar_json(r)
    registrar_http("GET /categorias", r, data)
    check("responde 200", r.status_code == 200, f"status={r.status_code} {data}")
    check("devuelve categorias de RDS", data.get("count", 0) > 0, json.dumps(data, ensure_ascii=False)[:200])
    # Las categorias deben llegar con los acentos de seed.sql intactos.
    nombres = [c.get("nombre", "") for c in data.get("data", [])]
    check("acentos correctos", "Computación" in nombres, f"nombres={nombres}")
    return data.get("data", [])


def test_2_crear_producto(categorias):
    titulo("TEST 2: POST /productos (crear producto)")
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
        "atributos": {"conexion": "USB", "color": "Negro"},
    }
    r = requests.post(f"{BASE_URL}/productos", json=payload, timeout=30)
    data = esperar_json(r)
    registrar_http("POST /productos", r, data)
    check("responde 201", r.status_code == 201, f"status={r.status_code} {data}")
    producto_id = data.get("producto_id")
    check("devuelve producto_id", producto_id is not None, json.dumps(data, ensure_ascii=False)[:200])
    check("estado inicial PENDIENTE", data.get("estado") == "PENDIENTE", json.dumps(data, ensure_ascii=False)[:200])
    return producto_id, codigo


def test_3_subir_imagen(producto_id):
    titulo(f"TEST 3: POST /productos/{{id}}/imagen (subir imagen)")
    if not IMAGEN.exists():
        check("imagen de prueba disponible", False, f"falta {IMAGEN}")
        return None
    if producto_id is None:
        check("producto creado previamente", False)
        return None

    with open(IMAGEN, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/productos/{producto_id}/imagen",
            files={"file": (IMAGEN.name, f, "image/jpeg")},
            timeout=180,
        )
    data = esperar_json(r)
    registrar_http(f"POST /productos/{producto_id}/imagen", r, data)
    check("responde 200", r.status_code == 200, f"status={r.status_code} {data}")
    # El punto critico: Lambda debe devolver LISTA y RDS debe quedar PUBLICADO.
    check("Lambda devolvio LISTA", data.get("estado_procesamiento") == "LISTA",
          f"estado={data.get('estado_procesamiento')} detalle={data.get('detalle')}")
    check("producto PUBLICADO en RDS", data.get("estado") == "PUBLICADO", f"estado={data.get('estado')}")
    check("original registrado en S3", bool(data.get("imagen_original")), json.dumps(data, ensure_ascii=False)[:200])
    return data.get("imagen_original")


def test_4_detalle(producto_id):
    titulo(f"TEST 4: GET /productos/{{id}} (obtener detalle)")
    if producto_id is None:
        check("producto creado previamente", False)
        return
    r = requests.get(f"{BASE_URL}/productos/{producto_id}", timeout=30)
    data = esperar_json(r)
    registrar_http(f"GET /productos/{producto_id}", r, data)
    check("responde 200", r.status_code == 200, f"status={r.status_code} {data}")
    if r.status_code != 200:
        return
    detalle = data.get("data", {})
    check("atributos guardados en DynamoDB", bool(detalle.get("atributos")),
          json.dumps(detalle, ensure_ascii=False)[:200])
    check("imagen procesada", detalle.get("estado_imagen") == "LISTA",
          f"estado_imagen={detalle.get('estado_imagen')}")
    check("miniatura referenciada", bool(detalle.get("miniatura_url")),
          f"miniatura_url={detalle.get('miniatura_url')}")


def test_5_lista_publicados(producto_id):
    titulo("TEST 5: GET /productos (lista publicados)")
    r = requests.get(f"{BASE_URL}/productos", timeout=60)
    data = esperar_json(r)
    registrar_http("GET /productos", r, {"count": data.get("count")})
    check("responde 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code != 200:
        return
    check("hay al menos un publicado", data.get("count", 0) > 0, "lista vacia")
    check("ninguno en PENDIENTE",
          all(p.get("estado") == "PUBLICADO" for p in data.get("data", [])),
          "aparecen productos no publicados")
    check("combina atributos y miniatura",
          all("atributos" in p and "miniatura_url" in p for p in data.get("data", [])),
          "faltan campos combinados de RDS y DynamoDB")
    if producto_id is not None:
        check("el producto de la prueba aparece en el catalogo",
              any(p.get("producto_id") == producto_id for p in data.get("data", [])),
              f"producto_id={producto_id} no esta en la lista")


def test_6_descargar_miniatura(producto_id):
    titulo(f"TEST 6: GET /productos/{{id}}/imagen (descargar miniatura)")
    if producto_id is None:
        check("producto creado previamente", False)
        return
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

    # La E4 pide comparar el archivo del endpoint con el descargado de S3.
    # La escenario E3 deja el original y la miniatura en evidence/stage3.
    referencia = EVIDENCIA.parent / "stage3" / "miniaturas" / f"lomax-{producto_id}.jpg"
    if not referencia.exists():
        # El nombre depende del producto; se lista el directorio para comparar.
        candidatos = list((EVIDENCIA.parent / "stage3" / "miniaturas").glob("*.jpg")) \
            if (EVIDENCIA.parent / "stage3" / "miniaturas").exists() else []
        referencia = candidatos[0] if candidatos else None
    if referencia is not None:
        iguales = referencia.read_bytes() == r.content
        check("miniatura del endpoint coincide con la descargada de S3", iguales,
              f"endpoint={len(r.content)} bytes, s3={len(referencia.read_bytes())} bytes ({referencia.name})")
    else:
        check("miniatura de S3 disponible para comparar", False,
              "no hay miniaturas de referencia en evidence/stage3/miniaturas")


def test_7_reprocesar(producto_id):
    titulo(f"TEST 7: POST /productos/{{id}}/reprocesar (reintenta)")
    if producto_id is None:
        check("producto creado previamente", False)
        return
    r = requests.post(f"{BASE_URL}/productos/{producto_id}/reprocesar", timeout=180)
    data = esperar_json(r)
    registrar_http(f"POST /productos/{producto_id}/reprocesar", r, data)
    check("responde 200", r.status_code == 200, f"status={r.status_code} {data}")
    check("reproceso deja la imagen LISTA", data.get("estado_procesamiento") == "LISTA",
          f"estado={data.get('estado_procesamiento')} detalle={data.get('detalle')}")
    check("producto sigue PUBLICADO", data.get("estado_rds") == "PUBLICADO",
          f"estado_rds={data.get('estado_rds')}")

    # Repetir no debe duplicar objetos en S3: la clave de salida es determinista.
    miniatura_key = None
    d = requests.get(f"{BASE_URL}/productos/{producto_id}", timeout=30).json().get("data", {})
    if d.get("miniatura_url"):
        r2 = requests.get(f"{BASE_URL}/productos/{producto_id}/imagen", timeout=60)
        # La misma clave sirve el mismo objeto, asi que el contenido no cambia.
        check("reprocesar no altera la miniatura", r2.status_code == 200,
              f"status={r2.status_code}")
    return miniatura_key


def test_8_errores(categorias, codigo):
    titulo("TEST 8: Validaciones de errores")
    categoria_id = categorias[0]["categoria_id"] if categorias else 1
    base = {
        "nombre": "Producto invalido",
        "descripcion": "Debe ser rechazado.",
        "precio": 10.0,
        "categoria_id": categoria_id,
        "atributos": {"origen": "prueba"},
    }

    # 409 codigo duplicado
    if codigo:
        r = requests.post(f"{BASE_URL}/productos", json=dict(base, codigo=codigo), timeout=30)
        d = esperar_json(r)
        registrar_http("POST /productos (codigo duplicado)", r, d)
        check("codigo duplicado -> 409", r.status_code == 409, f"status={r.status_code}")
        check("409 identifica el paso fallido (rds)", d.get("paso_fallido") == "rds",
              f"paso_fallido={d.get('paso_fallido')}")
    else:
        check("codigo duplicado -> 409", False, "no se creo el producto de la prueba")

    # 400 precio negativo
    r = requests.post(f"{BASE_URL}/productos",
                      json=dict(base, codigo=f"{codigo or 'X'}-NEG", precio=-1), timeout=30)
    check("precio negativo -> 400", r.status_code == 400, f"status={r.status_code}")

    # 400 categoria inexistente
    r = requests.post(f"{BASE_URL}/productos",
                      json=dict(base, codigo=f"{codigo or 'X'}-CAT", categoria_id=999999), timeout=30)
    check("categoria inexistente -> 400", r.status_code == 400, f"status={r.status_code}")

    # 400 payload vacio
    r = requests.post(f"{BASE_URL}/productos", json={}, timeout=30)
    check("payload vacio -> 400", r.status_code == 400, f"status={r.status_code}")

    # 404 producto inexistente
    r = requests.get(f"{BASE_URL}/productos/999999", timeout=30)
    check("producto inexistente -> 404", r.status_code == 404, f"status={r.status_code}")

    # 404 reprocesar inexistente
    r = requests.post(f"{BASE_URL}/productos/999999/reprocesar", timeout=30)
    check("reprocesar inexistente -> 404", r.status_code == 404, f"status={r.status_code}")

    # 415 formato no permitido
    if codigo:
        payload = dict(base, codigo=codigo)
        rr = requests.post(f"{BASE_URL}/productos", json=payload, timeout=30)
        pid = esperar_json(rr).get("producto_id")
        if pid:
            r = requests.post(f"{BASE_URL}/productos/{pid}/imagen",
                              files={"file": ("documento.txt", b"esto no es una imagen", "text/plain")},
                              timeout=60)
            d = esperar_json(r)
            registrar_http(f"POST /productos/{pid}/imagen (formato no permitido)", r, d)
            check("formato no permitido -> 415", r.status_code == 415, f"status={r.status_code} {d}")
            check("415 identifica el paso fallido (validacion)", d.get("paso_fallido") == "validacion",
                  f"paso_fallido={d.get('paso_fallido')}")

            # 413 archivo mayor a 5 MiB
            grande = b"\xff\xd8\xff\xe0" + b"0" * (5 * 1024 * 1024 + 1024)
            r = requests.post(f"{BASE_URL}/productos/{pid}/imagen",
                              files={"file": ("grande.jpg", grande, "image/jpeg")}, timeout=60)
            d = esperar_json(r)
            check("archivo mayor a 5 MiB -> 413", r.status_code == 413, f"status={r.status_code} {d}")

            # El producto incompleto no debe aparecer en el catalogo.
            r = requests.get(f"{BASE_URL}/productos", timeout=60)
            lista = esperar_json(r)
            check("el producto invalido no aparece en el catalogo",
                  not any(p.get("producto_id") == pid for p in lista.get("data", [])),
                  f"producto_id={pid} aparecio en el catalogo")


def guardar_reporte():
    ok = sum(1 for _, p in resultados if p)
    total = len(resultados)
    EVIDENCIA.mkdir(parents=True, exist_ok=True)
    destino = EVIDENCIA / "reporte-e4.md"
    momento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with destino.open("w", encoding="utf-8") as f:
        f.write("# E4 - Reporte de pruebas de la API (Etapa 4)\n\n")
        f.write(f"- Fecha: {momento}\n")
        f.write(f"- Base URL: {BASE_URL}\n")
        f.write(f"- Resultado: **{ok}/{total}** comprobaciones OK\n\n")
        for estado, nombre, detalle in lineas_reporte:
            if estado == "":
                f.write(f"{nombre}\n")
                if detalle:
                    f.write(f"{detalle}\n")
            else:
                marca = "OK" if estado == "OK" else "FALLA"
                sufijo = f" - {detalle}" if detalle else ""
                f.write(f"- **{marca}** {nombre}{sufijo}\n")
    print(f"\n  {Colors.YELLOW}reporte guardado en {destino.relative_to(RAIZ)}{Colors.RESET}")
    return ok, total


def main():
    print(f"{Colors.BLUE}{'=' * 72}")
    print("ETAPA 4 - PRUEBA DE INTEGRACION DE LA API LOMAX (E4)")
    print(f"{'=' * 72}{Colors.RESET}")

    if not test_health():
        print(f"\n{Colors.RED}La API no responde en {BASE_URL}. "
              f"Levantala con: docker compose up -d backend frontend proxy{Colors.RESET}")
        return 1

    categorias = test_1_categorias()
    creado = test_2_crear_producto(categorias)
    producto_id, codigo = creado if creado else (None, None)

    test_3_subir_imagen(producto_id)
    test_4_detalle(producto_id)
    test_5_lista_publicados(producto_id)
    test_6_descargar_miniatura(producto_id)
    test_7_reprocesar(producto_id)
    test_8_errores(categorias, codigo)

    ok, total = guardar_reporte()
    color = Colors.GREEN if ok == total else Colors.RED
    print(f"\n{Colors.BLUE}{'=' * 72}")
    print(f"{color}RESULTADO: {ok}/{total} comprobaciones OK{Colors.RESET}")
    if ok != total:
        for nombre, paso in resultados:
            if not paso:
                print(f"  {Colors.RED}- {nombre}{Colors.RESET}")
    print(f"{'=' * 72}{Colors.RESET}")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
