"""Excel con resultados de una búsqueda o con todo el índice. Las columnas salen de CAMPOS;
las fechas se guardan como fecha y los montos como número, para poder filtrarlos en Excel."""

import os
from datetime import date, datetime

from . import config
from .busqueda import Resultado, filas, nombre_tipo
from .campos import CAMPOS
from .indice import conectar, correcciones

ROJO, AMARILLO = "F8D7DA", "FFF3CD"
FORMATOS = {"fecha": "DD/MM/YYYY", "monto": "#,##0.00"}


def celda(campo, valor):
    if valor is None:
        return None
    if campo.tipo == "fecha":
        return date.fromisoformat(valor)
    if campo.nombre == "tipo":
        return nombre_tipo(valor)
    return valor


def a_excel(resultados, nombre="Resultados", busqueda=True, abrir=False):
    """Guarda los resultados en Resultados/<nombre>_<fecha>.xlsx. `busqueda`: incluir las
    columnas "Buscado" y "Resultado"."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    os.makedirs(config.SALIDAS, exist_ok=True)
    salida = os.path.join(config.SALIDAS, f"{nombre}_{datetime.now():%Y-%m-%d_%H%M%S}.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = nombre
    previas = [("Buscado", 18), ("Resultado", 28)] if busqueda else []
    columnas = previas + [(c.etiqueta, c.ancho) for c in CAMPOS] + [
        ("Nombre de archivo", 30), ("Carpeta", 50), ("Lectura dudosa", 16),
        ("Otras lecturas", 30), ("Corregido a mano", 40)]
    corregidos = correcciones(conectar())
    ws.append([t for t, _ in columnas])
    for r in resultados:
        f = r.fila or {}
        revisar = r.fila is not None and (bool(f["dudoso"]) or not f["numero"])
        ws.append(([r.buscado, r.etiqueta] if busqueda else [])
                  + [celda(c, f.get(c.nombre)) for c in CAMPOS]
                  + ([os.path.basename(f["ruta"]), os.path.dirname(f["ruta"]),
                      "SÍ - revisar" if revisar else "", f["alternativas"],
                      corregidos.get(f["ruta"])] if f else []))
        color = ROJO if r.fila is None else AMARILLO if (r.revisar or revisar) else None
        if color:
            for c in ws[ws.max_row]:
                c.fill = PatternFill("solid", fgColor=color)
        for i, c in enumerate(CAMPOS, len(previas) + 1):
            if c.tipo in FORMATOS:
                ws.cell(ws.max_row, i).number_format = FORMATOS[c.tipo]
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for i, (_, ancho) in enumerate(columnas, 1):
        ws.column_dimensions[get_column_letter(i)].width = ancho
    wb.save(salida)
    print(f"{len(resultados)} filas exportadas a: {salida}")
    if abrir and os.name == "nt":
        os.startfile(salida)
    return salida


def exportar_indice(abrir=False):
    """Todo el índice, ordenado por tipo y número."""
    con = conectar()
    todas = filas(con, " ORDER BY tipo, numero IS NULL, numero")
    return a_excel([Resultado("", "", f) for f in todas], "Indice", busqueda=False,
                   abrir=abrir)
