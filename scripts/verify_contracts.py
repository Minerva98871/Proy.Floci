#!/usr/bin/env python3
"""
Verificacion estatica de los contratos entre el backend y lambda/handler.py.

No necesita dependencias ni Docker: parsea el AST de los archivos y comprueba
que el evento que envia backend/lambda_service.py, los atributos de DynamoDB y
las claves de S3 usan los mismos nombres que espera y escribe la Lambda.

Uso:  python scripts/verify_contracts.py
Salida: 0 si todo coincide, 1 si hay algun desajuste.
"""

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HANDLER = RAIZ / "lambda" / "handler.py"
LAMBDA_SERVICE = RAIZ / "backend" / "lambda_service.py"
DYNAMODB_SERVICE = RAIZ / "backend" / "dynamodb_service.py"
S3_SERVICE = RAIZ / "backend" / "s3_service.py"
APP = RAIZ / "backend" / "app.py"

problemas = []


def cargar(ruta):
    return ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))


def claves_evento_que_lee_el_handler(tree):
    """Claves que el handler lee del evento: event.get("x") / event["x"]."""
    claves = set()
    for nodo in ast.walk(tree):
        if (
            isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Attribute)
            and isinstance(nodo.func.value, ast.Name)
            and nodo.func.value.id == "event"
            and nodo.func.attr in ("get", "setdefault")
            and nodo.args
            and isinstance(nodo.args[0], ast.Constant)
        ):
            claves.add(nodo.args[0].value)
        if (
            isinstance(nodo, ast.Subscript)
            and isinstance(nodo.value, ast.Name)
            and nodo.value.id == "event"
            and isinstance(nodo.slice, ast.Constant)
        ):
            claves.add(nodo.slice.value)
    return claves


def claves_payload_del_backend(tree):
    """Claves del dict de payload construido en invocar_procesar_imagen."""
    for funcion in ast.walk(tree):
        if not isinstance(funcion, ast.FunctionDef):
            continue
        if funcion.name != "invocar_procesar_imagen":
            continue
        for nodo in ast.walk(funcion):
            if isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Dict):
                claves = {
                    k.value
                    for k in nodo.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
                # El payload es el dict que contiene producto_id
                if "producto_id" in claves:
                    return claves
    return set()


def atributos_dynamodb(tree):
    """Nombres de atributo de DynamoDB en expresiones SET/REMOVE y en Items."""
    nombres = set()
    for nodo in ast.walk(tree):
        if not isinstance(nodo, ast.Constant) or not isinstance(nodo.value, str):
            continue
        texto = nodo.value
        if "imagen" in texto or texto in ("producto_id", "codigo", "atributos", "miniatura_key"):
            for parte in texto.replace(",", " ").replace("=", " ").split():
                if parte.isidentifier() and "imagen" in parte or parte in (
                    "producto_id", "codigo", "atributos", "miniatura_key"
                ):
                    nombres.add(parte)
    return nombres


def buscar_eval(tree):
    for nodo in ast.walk(tree):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) and nodo.func.id == "eval":
            return nodo.lineno
    return None


def main():
    print("Verificando contratos backend <-> lambda\n" + "-" * 52)

    # 1. Evento de invocacion
    leidas = claves_evento_que_lee_el_handler(cargar(HANDLER))
    enviadas = claves_payload_del_backend(cargar(LAMBDA_SERVICE))
    print(f"handler.py lee:      {sorted(leidas)}")
    print(f"lambda_service envia: {sorted(enviadas)}")

    faltantes = leidas - enviadas
    if faltantes:
        problemas.append(
            "El payload no incluye las claves que exige el handler: " + ", ".join(sorted(faltantes))
        )
    else:
        print("  [OK] el payload cubre todas las claves requeridas")

    sobrantes = enviadas - leidas
    if sobrantes:
        problemas.append(
            "El payload envia claves que el handler ignora: " + ", ".join(sorted(sobrantes))
        )

    # 2. Atributos de DynamoDB
    attrs_handler = atributos_dynamodb(cargar(HANDLER))
    attrs_backend = atributos_dynamodb(cargar(DYNAMODB_SERVICE))
    print(f"\nhandler.py usa:      {sorted(attrs_handler)}")
    print(f"dynamodb_service usa: {sorted(attrs_backend)}")

    if "imagen_estado" in attrs_handler and "estado_imagen" in attrs_backend:
        problemas.append(
            "El handler escribe 'imagen_estado' pero el backend lee/escribe 'estado_imagen'"
        )
    else:
        print("  [OK] el nombre del atributo de estado coincide")

    # 3. Clave de la miniatura
    app_texto = APP.read_text(encoding="utf-8")
    s3_texto = S3_SERVICE.read_text(encoding="utf-8")
    if "miniatura_key" not in s3_texto:
        problemas.append(
            "s3_service.py no recibe miniatura_key: la clave la calcula el handler "
            "y debe leerse de DynamoDB, no reconstruirse"
        )
    elif "miniatura_key" not in app_texto:
        problemas.append("app.py no pasa la clave de miniatura leida de DynamoDB")
    else:
        print("  [OK] la miniatura se resuelve con la clave de DynamoDB")

    # 4. eval() en el backend
    linea = buscar_eval(cargar(APP))
    if linea:
        problemas.append(f"app.py usa eval() en la linea {linea}: usar json.loads")
    else:
        print("  [OK] no hay eval() en app.py")

    print("\n" + "-" * 52)
    if problemas:
        print(f"{len(problemas)} problema(s):")
        for p in problemas:
            print(f"  - {p}")
        return 1

    print("Todos los contratos coinciden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
