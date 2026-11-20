"""Búsqueda por número de remito (de a uno o por lista), con coincidencias por pedido
informadas por separado y "casi coincidencias" para lecturas dudosas."""

import os
import re
import shutil
import sys
from datetime import datetime

from . import config
from .indice import conectar

SELECT = "SELECT ruta, remito, pedido, fecha, cliente FROM docs"


# ---------------------------------------------------------------- lógica pura (testeable)

def parsear_consulta(q):
    """Interpreta lo que escribió el usuario. Devuelve (punto_de_venta | None, numero).
    Acepta '43300', '00007-00043300', '00007 - 00043300', 'R 00007-00043300', 43300.0."""
    q = str(q).strip()
    if re.fullmatch(r"\d+\.0+", q):          # números que vienen de Excel como 43300.0
        q = q.split(".")[0]
    m = (re.search(r"(\d{1,5})\s*[-–—]\s*(\d{1,8})", q)
         or re.fullmatch(r"\s*(\d{1,5})\s+(\d{6,8})\s*", q))
    if m:
        return int(m.group(1)), int(m.group(2))
    dig = re.sub(r"\D", "", q)
    return (None, int(dig)) if dig else None


def coincide(campo, consulta):
    """¿Alguno de los números del campo ('PPPPP-NNNNNNNN;...') coincide con la consulta?"""
    pv_q, n_q = consulta
    for x in (campo or "").split(";"):
        if x:
            pv, n = (int(v) for v in x.split("-"))
            if n == n_q and (pv_q is None or pv == pv_q):
                return True
    return False


def distancia(a, b):
    """Distancia de edición (Levenshtein): dígitos a cambiar/agregar/quitar para ir de a a b."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def casi(dudosos, consulta, excluir=()):
    """Documentos con lectura dudosa cuyo número difiere en 1 dígito del buscado.
    Se compara el número elegido y las lecturas incompletas (dígitos de más/menos);
    las alternativas de 8 dígitos suelen ser errores del OCR y solo agregarían ruido."""
    pv_q, n_q = consulta
    q = f"{n_q:08d}"
    res = []
    for ruta, remito, pedido, fecha, cliente, alternativas in dudosos:
        if ruta in excluir:
            continue
        candidatos = [remito] + [x for x in (alternativas or "").split(";")
                                 if "-" in x and len(x.split("-", 1)[1]) != 8]
        for x in candidatos:
            if not x or "-" not in x:
                continue
            pv, n = x.split("-", 1)
            if pv_q is not None and int(pv) != pv_q:
                continue
            if distancia(n, q) <= 1:
                res.append((ruta, remito, pedido, fecha, cliente))
                break
    return res


# ---------------------------------------------------------------- consultas al índice

def cargar(con):
    todas = con.execute(SELECT).fetchall()
    dudosos = con.execute("SELECT ruta, remito, pedido, fecha, cliente, alternativas "
                          "FROM docs WHERE dudoso = 1").fetchall()
    return todas, dudosos


def resolver(con, todas, dudosos, consulta, texto_original):
    """Devuelve (por_remito, posibles, por_pedido).
    - por_remito: coincide el número de remito.
    - posibles: lecturas dudosas a 1 dígito, o documentos sin número detectado que
      contienen los dígitos en su texto. Hay que revisarlos a mano.
    - por_pedido: coincide el número de pedido (se informa aparte)."""
    por_remito = [r for r in todas if coincide(r[1], consulta)]
    por_pedido = [r for r in todas if coincide(r[2], consulta)]
    ya = {r[0] for r in por_remito} | {r[0] for r in por_pedido}
    posibles = casi(dudosos, consulta, ya)
    ya |= {r[0] for r in posibles}
    digitos = re.sub(r"\D", "", texto_original)
    if len(digitos) >= 4:
        posibles += [r for r in con.execute(
            SELECT + " WHERE (remito IS NULL OR remito = '') AND "
            "replace(replace(texto,' ',''),'-','') LIKE ?", (f"%{digitos}%",))
            if r[0] not in ya]
    return por_remito, posibles, por_pedido


# ---------------------------------------------------------------- comandos

def mostrar(filas):
    if not filas:
        print("Sin resultados.")
        return
    for ruta, remito, pedido, fecha, cliente in filas:
        print(f"{ruta}\n    remito: {remito or '-'}   fecha: {fecha or '-'}   "
              f"pedido: {pedido or '-'}\n    cliente: {cliente or '-'}")
    print(f"\n{len(filas)} resultado(s).")


def buscar_numero(q):
    consulta = parsear_consulta(q)
    if not consulta:
        sys.exit("Ingresá un número.")
    con = conectar()
    todas, dudosos = cargar(con)
    por_remito, posibles, por_pedido = resolver(con, todas, dudosos, consulta, q)

    print("=== POR NÚMERO DE REMITO ===")
    if por_remito:
        mostrar(por_remito)
    else:
        print("Sin coincidencia exacta." if posibles else "NO ENCONTRADO")
    if posibles:
        print("\nPOSIBLES (el número no se pudo leer con seguridad; abrirlos y confirmar):")
        mostrar(posibles)
    print("\n=== POR NÚMERO DE PEDIDO ===")
    if por_pedido:
        mostrar(por_pedido)
    else:
        print("NO ENCONTRADO")


def buscar_texto(q):
    con = conectar()
    palabras = q.lower().split()
    sql = SELECT + " WHERE " + " AND ".join(["lower(texto) LIKE ?"] * len(palabras))
    mostrar(con.execute(sql, [f"%{p}%" for p in palabras]).fetchall())


def leer_lista(ruta):
    """Lee los números a buscar: primera columna con datos de un Excel, o un TXT/CSV."""
    ruta = ruta.strip().strip('"')
    ext = os.path.splitext(ruta)[1].lower()
    valores = []
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        ws = openpyxl.load_workbook(ruta, read_only=True, data_only=True).worksheets[0]
        columnas = {}
        for fila in ws.iter_rows(values_only=True):
            for i, v in enumerate(fila):
                if v is not None and str(v).strip():
                    columnas.setdefault(i, []).append(v)
        if columnas:
            valores = columnas[min(columnas)]
    elif ext == ".xls":
        sys.exit("El archivo es .xls (Excel viejo). Guardalo como .xlsx, o copiá la columna "
                 "y pegala en la opción de Bloc de notas.")
    else:
        with open(ruta, encoding="utf-8-sig", errors="replace") as f:
            for linea in f:
                linea = linea.strip()
                if linea:
                    valores.append(linea if re.search(r"\d\s*[-–—]\s*\d", linea)
                                   else re.split(r"[;\t,]", linea)[0])
    return [str(v).strip() for v in valores if re.search(r"\d", str(v))]  # sin encabezados


def _copiar(rutas, carpeta):
    unicos = list(dict.fromkeys(rutas))
    os.makedirs(carpeta, exist_ok=True)
    for r in unicos:
        destino = os.path.join(carpeta, os.path.basename(r))
        base, ext = os.path.splitext(destino)
        k = 2
        while os.path.exists(destino):
            destino = f"{base} ({k}){ext}"
            k += 1
        shutil.copy2(r, destino)
    return len(unicos)


def buscar_lista(entrada, salida="auto", copiar=None, abrir=False):
    """Busca una lista de números y genera un Excel con dos hojas: 'Por remito' y
    'Por pedido', con una fila por número buscado (NO ENCONTRADO en rojo)."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    sello = datetime.now().strftime("%Y-%m-%d_%H%M")
    if salida == "auto":
        salida = os.path.join(config.SALIDAS, f"Resultados_{sello}.xlsx")
    if copiar == "auto":
        copiar = os.path.join(config.SALIDAS, f"Encontrados_{sello}")

    consultas = leer_lista(entrada)
    if not consultas:
        sys.exit("No encontré números en el archivo.")
    print(f"{len(consultas)} números para buscar...")
    con = conectar()
    todas, dudosos = cargar(con)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Por remito"
    wp = wb.create_sheet("Por pedido")
    titulos = ["Número buscado", "Resultado", "Nombre de archivo", "Remito", "Fecha",
               "Cliente", "Pedido", "Carpeta"]
    ws.append(titulos)
    wp.append(titulos)
    rojo = PatternFill("solid", fgColor="F8D7DA")
    amarillo = PatternFill("solid", fgColor="FFF3CD")

    def fila(hoja, q, etiqueta, r=None, color=None):
        if r:
            ruta, remito, pedido, fecha, cliente = r
            hoja.append([q, etiqueta, os.path.basename(ruta), remito, fecha, cliente,
                         pedido, os.path.dirname(ruta)])
        else:
            hoja.append([q, etiqueta])
        if color:
            for c in hoja[hoja.max_row]:
                c.fill = color

    ok_remito = ok_pedido = 0
    archivos, archivos_pedido = [], []
    for q in consultas:
        consulta = parsear_consulta(q)
        por_remito, posibles, por_pedido = (resolver(con, todas, dudosos, consulta, q)
                                            if consulta else ([], [], []))
        if por_remito or posibles:
            ok_remito += 1
            for r in por_remito:
                fila(ws, q, "Encontrado", r)
                archivos.append(r[0])
            for r in posibles:
                fila(ws, q, "Posible (revisar)", r, amarillo)
                archivos.append(r[0])
        else:
            fila(ws, q, "NO ENCONTRADO", color=rojo)
        if por_pedido:
            ok_pedido += 1
            for r in por_pedido:
                fila(wp, q, "Encontrado", r)
                archivos_pedido.append(r[0])
        else:
            fila(wp, q, "NO ENCONTRADO", color=rojo)

    for hoja in (ws, wp):
        for c in hoja[1]:
            c.font = Font(bold=True)
        hoja.freeze_panes = "A2"
        hoja.auto_filter.ref = hoja.dimensions
        for col, ancho in zip("ABCDEFGH", (20, 24, 30, 18, 12, 35, 18, 50)):
            hoja.column_dimensions[col].width = ancho
    wb.save(salida)

    n = len(consultas)
    print(f"Por remito -> encontrados: {ok_remito}   no encontrados: {n - ok_remito}")
    print(f"Por pedido -> encontrados: {ok_pedido}   no encontrados: {n - ok_pedido}")
    print(f"Resultado guardado en: {salida}")

    if copiar and (archivos or archivos_pedido):
        if archivos:
            print(f"Copié {_copiar(archivos, copiar)} remitos encontrados a: {copiar}")
        if archivos_pedido:
            sub = os.path.join(copiar, "Coincidencias por pedido")
            print(f"Copié {_copiar(archivos_pedido, sub)} coincidencias por pedido a: {sub}")
        if abrir and os.name == "nt":
            os.startfile(copiar)
    if abrir and os.name == "nt":
        os.startfile(salida)
    return salida
