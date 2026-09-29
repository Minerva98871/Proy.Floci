"""
Anade marca de orden de bytes (BOM) UTF-8 a los scripts de PowerShell.

Windows PowerShell 5.1 interpreta un archivo .ps1 SIN BOM como ANSI (cp1252),
no como UTF-8. Eso convierte cada tilde y enye en dos caracteres basura y
corrompe los comentarios en espanol. Con la BOM, 5.1 lee el archivo como UTF-8
correctamente.

Se ejecuta sobre todos los .ps1 del repositorio y es idempotente: un archivo
que ya tiene BOM no se modifica.

Uso:  python scripts/fix_powershell_encoding.py
"""

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BOM = b"\xef\xbb\xbf"

# Un texto UTF-8 releido como cp1252 y guardado otra vez como UTF-8 duplica la
# codificacion: la "u" acentuada pasa a ser un par de caracteres que empiezan
# por A-tilde y terminan en el simbolo de ordinal masculino. El patron detectable
# es un lead byte UTF-8 de dos bytes (C2-F4) seguido de su byte de continuacion
# (80-BF), ambos interpretados como latin-1.
#
# Solo se usa para DIAGNOSTICAR, no para reparar automaticamente: el patron
# tambien puede aparecer legitimamente en un documento que este hablando
# justamente de este fallo, como hacia este mismo archivo. Reparar sin mirar
# destrozaria esos casos. Para corregir de verdad, la via segura es reescribir la
# linea afectada con la acentuacion correcta.
MOJIBAKE = re.compile("[\u00c2-\u00f4][\u0080-\u00bf]")


def main() -> int:
    extensiones = (
        "*.ps1", "*.md", "*.yaml", "*.yml", "*.py", "*.js", "*.html",
        "*.css", "*.conf", "*.template", "*.txt",
    )
    ignorados = {".git", "node_modules", ".venv", "venv"}

    modificados = 0
    yaTenian = 0
    sospechosos = []

    for patron in extensiones:
        for ruta in sorted(RAIZ.rglob(patron)):
            if any(parte in ignorados for parte in ruta.parts):
                continue

            crudo = ruta.read_bytes()
            if not crudo:
                continue

            # 1) Diagnostico de doble codificacion.
            texto = crudo.decode("utf-8-sig", errors="replace")
            for numero, linea in enumerate(texto.splitlines(), 1):
                coincidencias = MOJIBAKE.findall(linea)
                if coincidencias:
                    sospechosos.append(
                        f"{ruta.relative_to(RAIZ)}:{numero}  "
                        f"{len(coincidencias)} coincidencia/s  {linea.strip()[:90]}"
                    )

            # 2) BOM en los .ps1, que es lo que los hace UTF-8 en PowerShell 5.1.
            if ruta.suffix == ".ps1" and not crudo.startswith(BOM):
                crudo = BOM + crudo
                modificados += 1
                print(f"  BOM anadido: {ruta.relative_to(RAIZ)}")
            elif ruta.suffix == ".ps1":
                yaTenian += 1

            if crudo != ruta.read_bytes():
                ruta.write_bytes(crudo)

    print(
        f"{modificados} scripts con BOM anadido, {yaTenian} ya estaban bien."
    )
    if sospechosos:
        print()
        print("POSIBLE DOBLE CODIFICACION (revisar a mano, no se corrige solo):")
        for linea in sospechosos:
            print(f"  {linea}")
        return 1
    print("Sin doble codificacion detectada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
