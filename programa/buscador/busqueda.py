"""Búsqueda en el índice: filtros (tipo, fechas, monto, clientes, texto), números de a uno o
en lista (con "casi coincidencias" para lecturas dudosas) y documentos vinculados (los
remitos de una factura y viceversa)."""

import os
import re
import shutil
from dataclasses import dataclass, field

from . import config
from .campos import CAMPOS, POR_NOMBRE, normalizar, plano

COLUMNAS = ["ruta", "dudoso", "alternativas"] + [c.nombre for c in CAMPOS]
SELECT = f"SELECT {', '.join(COLUMNAS)} FROM docs"
OTROS_NUMEROS = [c.nombre for c in CAMPOS if c.buscar_por_numero]
OPERADORES_MONTO = ("<", ">", "=")


def nombre_tipo(clave):
    t = config.CFG.tipos.get(clave)
    return t.nombre if t else (clave or "Documento")


# ---------------------------------------------------------------- números (lógica pura)

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
    for f in dudosos:
        if f["ruta"] in excluir:
            continue
        candidatos = [f["numero"]] + [x for x in (f["alternativas"] or "").split(";")
                                      if "-" in x and len(x.split("-", 1)[1]) != 8]
        for x in candidatos:
            if not x or "-" not in x:
                continue
            pv, n = x.split("-", 1)
            if pv_q is not None and int(pv) != pv_q:
                continue
            if distancia(n, q) <= 1:
                res.append(f)
                break
    return res


# ---------------------------------------------------------------- filtros

def condicion_cliente(x):
    """Un cliente escrito por el usuario: CUIT (11 dígitos), código (solo dígitos) o parte
    del nombre (sin distinguir mayúsculas ni acentos)."""
    x = str(x).strip()
    if len(re.sub(r"\D", "", x)) == 11 and re.fullmatch(r"[\d\s.\-]+", x):
        return "cuit = ?", normalizar("cuit", x)
    if x.isdigit():
        return "cod_cliente = ?", normalizar("codigo", x)
    return "plano(cliente) LIKE ?", f"%{plano(x)}%"


@dataclass
class Filtro:
    numeros: list = field(default_factory=list)
    tipo: str | None = None         # clave de config.toml ("remito", "factura"...)
    desde: str | None = None        # aaaa-mm-dd
    hasta: str | None = None
    monto_op: str | None = None     # '<', '>' o '='
    monto: float | None = None
    clientes: list = field(default_factory=list)
    texto: str | None = None

    def vacio(self):
        return not (self.numeros or self.tipo or self.desde or self.hasta or self.clientes
                    or self.texto or (self.monto_op and self.monto is not None))

    def where(self):
        """(' WHERE ...', parámetros) con todos los filtros menos los números."""
        cond, params = [], []
        if self.tipo:
            cond.append("tipo = ?")
            params.append(self.tipo)
        if self.desde:
            cond.append("fecha >= ?")
            params.append(self.desde)
        if self.hasta:
            cond.append("fecha <= ?")
            params.append(self.hasta)
        if self.monto_op in OPERADORES_MONTO and self.monto is not None:
            cond.append("abs(monto - ?) < 0.005" if self.monto_op == "=" else
                        f"monto {self.monto_op} ?")
            params.append(self.monto)
        if self.clientes:
            partes = [condicion_cliente(c) for c in self.clientes]
            cond.append("(" + " OR ".join(p[0] for p in partes) + ")")
            params += [p[1] for p in partes]
        for palabra in (self.texto or "").split():   # LIKE de SQLite: rápido sobre el texto
            cond.append("texto LIKE ?")                # completo y sin distinguir mayúsculas
            params.append(f"%{palabra}%")
        return (" WHERE " + " AND ".join(cond)) if cond else "", params


# ---------------------------------------------------------------- consultas al índice

@dataclass
class Resultado:
    buscado: str                    # el número buscado ("" si se buscó solo con filtros)
    etiqueta: str                   # "Encontrado", "Posible (revisar)", "Por pedido"...
    fila: dict | None = None        # None: no encontrado
    revisar: bool = False
    secundario: bool = False        # coincide por otro número (pedido): se copia aparte
    vinculado: bool = False


def filas(con, where="", params=()):
    return [dict(zip(COLUMNAS, r)) for r in con.execute(SELECT + where, params)]


class Numeros:
    """Número → documentos, por campo. Se arma una vez por búsqueda para no recorrer todo
    el índice por cada número buscado (con 200 números y 50.000 documentos: de ~20 s a <1 s)."""

    def __init__(self, documentos, campos):
        self.mapa = {c: {} for c in campos}
        for f in documentos:
            for c in campos:
                for x in filter(None, (f[c] or "").split(";")):
                    pv, n = x.split("-")
                    self.mapa[c].setdefault(int(n), []).append((int(pv), f))

    def buscar(self, campo, consulta):
        pv_q, n_q = consulta
        return [f for pv, f in self.mapa[campo].get(n_q, []) if pv_q is None or pv == pv_q]


def resolver(con, numeros, dudosos, consulta, original, where="", params=()):
    """Devuelve (exactos, posibles, otros):
    - exactos: coincide el número del documento.
    - posibles: lecturas dudosas a 1 dígito, o documentos sin número detectado que contienen
      los dígitos en su texto. Hay que revisarlos a mano.
    - otros: {campo: documentos} que coinciden por otro número (el pedido)."""
    exactos = numeros.buscar("numero", consulta)
    otros = {n: numeros.buscar(n, consulta) for n in OTROS_NUMEROS}
    ya = {f["ruta"] for f in exactos} | {f["ruta"] for fs in otros.values() for f in fs}
    posibles = casi(dudosos, consulta, ya)
    ya |= {f["ruta"] for f in posibles}
    digitos = re.sub(r"\D", "", str(original))
    if len(digitos) >= 4:
        sql = (where + (" AND " if where else " WHERE ") + "numero IS NULL AND "
               "replace(replace(texto, ' ', ''), '-', '') LIKE ?")
        posibles += [f for f in filas(con, sql, [*params, f"%{digitos}%"]) if f["ruta"] not in ya]
    return exactos, posibles, otros


def vinculados(numeros, fila):
    """Documentos de otro tipo vinculados a `fila`: los que cita (por ejemplo, los remitos
    de una factura), los que la citan y los que comparten número de pedido.
    `numeros`: Numeros de TODO el índice con los campos numero, citados y pedido."""
    def lista(campo):
        return [parsear_consulta(x) for x in filter(None, (fila[campo] or "").split(";"))]

    candidatos = ([f for c in lista("citados") for f in numeros.buscar("numero", c)]
                  + [f for c in lista("numero") for f in numeros.buscar("citados", c)]
                  + [f for c in lista("pedido") for f in numeros.buscar("pedido", c)])
    unicos = {f["ruta"]: f for f in candidatos
              if f["tipo"] != fila["tipo"] and f["ruta"] != fila["ruta"]}
    return sorted(unicos.values(), key=lambda f: (f["tipo"] or "", f["numero"] or ""))


def _con_vinculados(con, resultados):
    numeros = Numeros(filas(con), ["numero", "citados", "pedido"])
    salida = []
    for r in resultados:
        salida.append(r)
        if r.fila:
            de = f"{nombre_tipo(r.fila['tipo']).lower()} {r.fila['numero'] or ''}".strip()
            salida += [Resultado(r.buscado, f"{nombre_tipo(f['tipo'])} de {de}", f,
                                 revisar=bool(f["dudoso"]), secundario=r.secundario,
                                 vinculado=True)
                       for f in vinculados(numeros, r.fila)]
    return salida


def buscar(con, filtro, con_vinculados=False):
    """Busca según el filtro. Con números: una o más filas por número buscado (incluye
    'NO ENCONTRADO'). Sin números: los documentos que cumplen los filtros."""
    where, params = filtro.where()
    if not filtro.numeros:
        res = [Resultado("", "", f, revisar=bool(f["dudoso"]))
               for f in filas(con, where + " ORDER BY fecha, numero", params)]
    else:
        todas = filas(con, where, params)
        numeros = Numeros(todas, ["numero"] + OTROS_NUMEROS)
        dudosos = [f for f in todas if f["dudoso"]]
        res = []
        for q in filtro.numeros:
            c = parsear_consulta(q)
            exactos, posibles, otros = (resolver(con, numeros, dudosos, c, q, where, params)
                                        if c else ([], [], {}))
            r = ([Resultado(q, "Encontrado", f) for f in exactos]
                 + [Resultado(q, "Posible (revisar)", f, revisar=True) for f in posibles])
            hubo = bool(r)
            for nombre, fs in otros.items():
                et = POR_NOMBRE[nombre].etiqueta.lower()
                r += [Resultado(q, f"Por {et}" if hubo else f"Solo por {et} (revisar)", f,
                                revisar=not hubo, secundario=True) for f in fs]
            res += r or [Resultado(q, "NO ENCONTRADO", revisar=True)]
    return _con_vinculados(con, res) if con_vinculados else res


# ---------------------------------------------------------------- listas y archivos

def leer_lista(ruta):
    """Lee valores de una lista: primera columna con datos de un Excel, o un TXT/CSV.
    Ignora los encabezados (renglones sin dígitos)."""
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
        raise ValueError("El archivo es .xls (Excel viejo). Guardalo como .xlsx, o copiá la "
                         "columna y pegala en el buscador.")
    else:
        with open(ruta, encoding="utf-8-sig", errors="replace") as f:
            for linea in f:
                linea = linea.strip()
                if linea:
                    valores.append(linea if re.search(r"\d\s*[-–—]\s*\d", linea)
                                   else re.split(r"[;\t,]", linea)[0])
    return [str(v).strip() for v in valores if re.search(r"\d", str(v))]


def copiar(rutas, carpeta):
    """Copia los archivos (sin repetir ni pisar nombres). Saltea los que ya no existen."""
    unicos = [r for r in dict.fromkeys(rutas) if os.path.exists(r)]
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
