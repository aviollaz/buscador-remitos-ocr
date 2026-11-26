"""Extracción de datos del texto leído por OCR: número de remito, pedido, fecha y cliente.

Funciones puras (sin OCR ni base de datos), fáciles de testear.
"""

import re
from collections import Counter
from datetime import date

from .config import DOC

# Formato de número de comprobante: punto de venta (4-5 dígitos) + número (8 dígitos).
# Ej.: 0001-00012345, 00007 - 00043300.
RE_NUM = re.compile(r"(?<!\d)(\d{4,5})\s*[-–—]\s*(\d{6,8})(?!\d)")
# Versión "cruda": acepta números con dígitos de más o de menos, para detectar lecturas dudosas.
RE_NUM_CRUDO = re.compile(r"(?<!\d)(\d{4,5})\s*[-–—]\s*(\d{5,9})(?!\d)")

_palabras = "|".join(re.escape(p) for p in DOC["palabras_pedido"])
RE_PEDIDO = re.compile(rf"(?:{_palabras})[^\n\d]{{0,25}}(\d{{4,5}})\s*[-–—]\s*(\d{{6,8}})", re.I)

# "Fecha: 25/11/2025" (prioridad) o cualquier fecha suelta como respaldo.
RE_FECHA = re.compile(r"Fecha\s*[:;]\s*(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{2,4})", re.I)
RE_FECHA_SUELTA = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)")

RE_CLIENTE = re.compile(
    rf"\b{DOC['etiqueta_cliente']}\b\s*[:;.]?\s*(.+?)(?=\s+{DOC['fin_cliente']}\b|\n|$)", re.I)

ANIO_MAX = date.today().year + 1


def norm(pv, n):
    """Normaliza un número de comprobante a PPPPP-NNNNNNNN."""
    return f"{int(pv):05d}-{int(n):08d}"


def fecha_valida(d, m, y, permitir_2_digitos=True):
    if not (1 <= d <= 31 and 1 <= m <= 12):
        return False
    return (permitir_2_digitos and y < 100) or 2000 <= y <= ANIO_MAX


def extraer(texto):
    """Devuelve (remitos, pedidos, fecha, cliente) a partir del texto de la página."""
    pedidos = {norm(*m.groups()) for m in RE_PEDIDO.finditer(texto)}
    remitos = []
    for m in RE_NUM.finditer(texto):
        n = norm(*m.groups())
        if n not in pedidos and n not in remitos:
            remitos.append(n)

    fecha = ""
    for m in list(RE_FECHA.finditer(texto)) + list(RE_FECHA_SUELTA.finditer(texto)):
        antes = texto[max(0, m.start() - 15):m.start()].lower()
        if "vto" in antes or "activ" in antes:   # vencimiento del CAI / inicio de actividades
            continue
        d, mth, y = (int(x) for x in m.groups())
        if fecha_valida(d, mth, y):
            fecha = f"{d:02d}/{mth:02d}/{y}"
            break

    c = RE_CLIENTE.search(texto)
    cliente = c.group(1).strip(" :;.-") if c else ""
    return ";".join(remitos), ";".join(sorted(pedidos)), fecha, cliente


def fecha_de_encabezado(texto_enc):
    """Primera fecha válida en la relectura de la zona del número (solo dígitos)."""
    for m in RE_FECHA_SUELTA.finditer(texto_enc):
        d, mth, y = (int(x) for x in m.groups())
        if fecha_valida(d, mth, y, permitir_2_digitos=False):
            return f"{d:02d}/{mth:02d}/{y}"
    return ""


def decidir(texto, lecturas_enc, texto_enc):
    """Elige el número de remito combinando dos lecturas independientes:
    - la de la página completa (OCR general), y
    - la de la zona del número releída solo con dígitos (más confiable, pesa doble).

    Devuelve (remito, dudoso, alternativas). Una lectura es "dudosa" si las lecturas no
    coinciden, si alguna tiene dígitos de más/menos, o si la zona no dio ningún número.
    """
    pedidos = {norm(*m.groups()) for m in RE_PEDIDO.finditer(texto)}
    pagina = [(a, b) for a, b in RE_NUM_CRUDO.findall(texto) if norm(a, b) not in pedidos]

    votos = Counter()
    for a, b in lecturas_enc:
        if len(b) == 8:
            votos[norm(a, b)] += 2
    for a, b in pagina:
        if len(b) == 8:
            votos[norm(a, b)] += 1

    crudas = {f"{int(a):05d}-{b}" for a, b in lecturas_enc}
    crudas |= {f"{int(a):05d}-{b}" for a, b in pagina}
    if not votos:
        # Ninguna lectura de 8 dígitos. Si hay de 9, lo más común es que una firma o raya
        # pegada al número se haya leído como un dígito extra al final: se trunca.
        for a, b in lecturas_enc + pagina:
            if len(b) == 9:
                votos[norm(a, b[:8])] += 1
        if not votos:
            return "", bool(crudas), ";".join(sorted(crudas))
        remito = votos.most_common(1)[0][0]
        return remito, True, ";".join(sorted(crudas - {remito}))

    remito = votos.most_common(1)[0][0]
    alternativas = sorted(crudas - {remito})
    dudoso = bool(alternativas) or (not lecturas_enc and bool(texto_enc))
    return remito, dudoso, ";".join(alternativas)
