"""Exportación del índice completo a CSV o Excel (para buscar con Ctrl+F o filtros)."""

import csv
import os
from datetime import datetime

from . import config
from .indice import conectar

_ORDEN = "ORDER BY remito = '', remito"


def exportar_csv(salida):
    con = conectar()
    with open(salida, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["archivo", "remito", "fecha", "cliente", "pedido", "dudoso"])
        w.writerows(con.execute(
            f"SELECT ruta, remito, fecha, cliente, pedido, dudoso FROM docs {_ORDEN}"))
    print(f"Exportado a {salida}")


def exportar_excel(salida=None, abrir=False):
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    salida = salida or os.path.join(
        config.SALIDAS, f"Indice_remitos_{datetime.now():%Y-%m-%d_%H%M}.xlsx")
    os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
    con = conectar()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Remitos"
    amarillo = PatternFill("solid", fgColor="FFF3CD")
    ws.append(["Remito", "Fecha", "Cliente", "Pedido", "Nombre de archivo", "Carpeta",
               "Lectura dudosa", "Otras lecturas"])
    n = 0
    for ruta, remito, fecha, cliente, pedido, dudoso, alt in con.execute(
            f"SELECT ruta, remito, fecha, cliente, pedido, dudoso, alternativas FROM docs "
            f"{_ORDEN}"):
        revisar = bool(dudoso) or not remito
        ws.append([remito or "(no detectado)", fecha, cliente, pedido,
                   os.path.basename(ruta), os.path.dirname(ruta),
                   "SÍ - revisar" if revisar else "", alt])
        if revisar:
            for c in ws[ws.max_row]:
                c.fill = amarillo
        n += 1
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col, ancho in zip("ABCDEFGH", (18, 12, 35, 18, 30, 50, 16, 30)):
        ws.column_dimensions[col].width = ancho
    wb.save(salida)
    print(f"{n} remitos exportados a: {salida}")
    if abrir and os.name == "nt":
        os.startfile(salida)
    return salida
