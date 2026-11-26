"""Interfaz de línea de comandos."""

import argparse
import os
import re
import sys

from .config import ErrorConfig


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


def filtro_desde_args(a):
    from .busqueda import Filtro, leer_lista
    from .campos import normalizar

    numeros = list(a.numeros) + (leer_lista(a.lista) if a.lista else [])
    op = valor = None
    if a.monto:
        m = re.fullmatch(r"\s*([<>=])\s*(.+)", a.monto)
        if not m or normalizar("monto", m.group(2)) is None:
            sys.exit("--monto: usá por ejemplo \">1000\", \"<500,50\" o \"=1234,56\".")
        op, valor = m.group(1), normalizar("monto", m.group(2))
    fechas = {k: normalizar("fecha", getattr(a, k)) for k in ("desde", "hasta")}
    for k, v in fechas.items():
        if getattr(a, k) and not v:
            sys.exit(f"--{k}: fecha inválida ({getattr(a, k)}); usá dd/mm/aaaa.")
    return Filtro(numeros=numeros, tipo=a.tipo, desde=fechas["desde"],
                  hasta=fechas["hasta"], monto_op=op, monto=valor,
                  clientes=a.cliente or [], texto=a.texto)


def imprimir(resultados):
    from .busqueda import nombre_tipo
    from .campos import CAMPOS, mostrar

    for r in resultados:
        cabeza = " | ".join(x for x in (r.buscado, r.etiqueta) if x)
        if not r.fila:
            print(f"{cabeza}")
            continue
        datos = "   ".join(
            f"{c.etiqueta.lower()}: {nombre_tipo(v) if c.nombre == 'tipo' else mostrar(c.tipo, v)}"
            for c in CAMPOS if (v := r.fila[c.nombre]) is not None)
        print(f"{cabeza + ': ' if cabeza else ''}{r.fila['ruta']}\n    {datos}")
    print(f"\n{len(resultados)} resultado(s).")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="buscador",
        description="Indexa remitos y facturas (OCR local) y permite buscarlos con filtros.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("indexar", help="leer una carpeta (y subcarpetas) y armar el índice")
    p.add_argument("carpeta")
    p.add_argument("--workers", type=int, default=None, help="procesos en paralelo")

    p = sub.add_parser("buscar", help="buscar por números y/o filtros")
    p.add_argument("numeros", nargs="*", help="números de comprobante")
    p.add_argument("--lista", help="Excel/TXT con números (primera columna)")
    p.add_argument("--tipo", help="remito, factura... (ver config.toml)")
    p.add_argument("--desde", help="fecha dd/mm/aaaa")
    p.add_argument("--hasta", help="fecha dd/mm/aaaa")
    p.add_argument("--monto", help='">1000", "<500", "=1234,56"')
    p.add_argument("--cliente", action="append", help="nombre, código o CUIT (repetible)")
    p.add_argument("--texto", help="palabras que contiene el documento")
    p.add_argument("--vinculados", action="store_true",
                   help="incluir los documentos vinculados (remitos de una factura, etc.)")
    p.add_argument("--excel", action="store_true", help="guardar el resultado en Excel")

    p = sub.add_parser("excel", help="exportar todo el índice a Excel")
    p.add_argument("--abrir", action="store_true")
    sub.add_parser("verificar", help="comprobar la instalación de Tesseract")
    sub.add_parser("gui", help="abrir la ventana del buscador")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "indexar":
            from .indice import indexar
            indexar(a.carpeta, a.workers)
        elif a.cmd == "buscar":
            from .busqueda import buscar
            from .indice import conectar
            filtro = filtro_desde_args(a)
            if filtro.vacio():
                sys.exit("Indicá algún número o filtro (ver: buscar --help).")
            resultados = buscar(conectar(), filtro, a.vinculados)
            imprimir(resultados)
            if a.excel:
                from .exportar import a_excel
                a_excel(resultados, abrir=True)
        elif a.cmd == "excel":
            from .exportar import exportar_indice
            exportar_indice(abrir=a.abrir)
        elif a.cmd == "verificar":
            verificar()
        elif a.cmd == "gui":
            from .gui import main as gui
            gui()
    except ErrorConfig as e:
        if a.cmd == "gui" and os.name == "nt":      # sin consola: mostrarlo en una ventana
            from tkinter import Tk, messagebox
            Tk().withdraw()
            messagebox.showerror("Buscador: error en config.toml", str(e))
        sys.exit(f"ERROR en la configuración: {e}")
