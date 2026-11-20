"""Interfaz de línea de comandos."""

import argparse
import sys


def verificar():
    import pytesseract

    from . import ocr  # configura la ruta de Tesseract y del idioma
    try:
        v = pytesseract.get_tesseract_version()
        langs = pytesseract.get_languages(config="")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"ERROR: no se pudo usar Tesseract ({e})")
    print(f"Tesseract {v} OK. Idiomas: {', '.join(langs)}")
    if ocr.IDIOMA not in langs:
        sys.exit(f"ERROR: falta el idioma '{ocr.IDIOMA}'.")
    print("Todo listo.")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="buscar_remitos",
        description="Indexa remitos escaneados con OCR local y permite buscarlos.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("indexar", help="leer una carpeta (y subcarpetas) y armar el índice")
    p.add_argument("carpeta")
    p.add_argument("--workers", type=int, default=None, help="procesos en paralelo")

    sub.add_parser("buscar", help="buscar un número de remito").add_argument("numero")
    sub.add_parser("texto", help="buscar texto (cliente, CUIT...)").add_argument("consulta")

    p = sub.add_parser("lista", help="buscar una lista de números (.xlsx/.txt) → Excel")
    p.add_argument("entrada")
    p.add_argument("salida", nargs="?", default="auto")
    p.add_argument("--copiar", help="carpeta donde copiar los encontrados ('auto' = nueva)")
    p.add_argument("--abrir", action="store_true", help="abrir el resultado (Windows)")

    p = sub.add_parser("excel", help="exportar todo el índice a Excel")
    p.add_argument("--abrir", action="store_true")
    sub.add_parser("exportar", help="exportar todo el índice a CSV").add_argument("salida")
    sub.add_parser("verificar", help="comprobar la instalación de Tesseract")

    a = ap.parse_args(argv)
    if a.cmd == "indexar":
        from .indice import indexar
        indexar(a.carpeta, a.workers)
    elif a.cmd == "buscar":
        from .busqueda import buscar_numero
        buscar_numero(a.numero)
    elif a.cmd == "texto":
        from .busqueda import buscar_texto
        buscar_texto(a.consulta)
    elif a.cmd == "lista":
        from .busqueda import buscar_lista
        buscar_lista(a.entrada, a.salida, a.copiar, a.abrir)
    elif a.cmd == "excel":
        from .exportar import exportar_excel
        exportar_excel(abrir=a.abrir)
    elif a.cmd == "exportar":
        from .exportar import exportar_csv
        exportar_csv(a.salida)
    elif a.cmd == "verificar":
        verificar()
