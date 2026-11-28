"""Extracción de datos del texto leído: tipo de documento, número y los campos de CAMPOS.

Funciones puras (sin OCR ni base de datos): el resultado depende solo del texto, del texto
de la zona del número y de la configuración. Por eso el índice puede recalcular todo cuando
cambia config.toml, sin volver a leer los archivos."""

import re
from collections import Counter

from . import config
from .campos import CAMPOS, POR_NOMBRE, RE_FECHA, comprobante, fecha_iso, monto, normalizar

# Lectura de la zona del número (solo dígitos, '-' y '/'): acepta dígitos de más o de menos
# para detectar lecturas dudosas.
RE_NUM_CRUDO = re.compile(r"(?<!\d)(\d{4,5})\s*[-–—]\s*(\d{5,9})(?!\d)")
# Separa las lecturas independientes de la zona (y las páginas) dentro de texto_zona; ninguna
# expresión puede cruzarlo, así el final de una lectura no se pega al principio de otra.
SEPARADOR_LECTURAS = "\n#\n"
# Importe con exactamente 2 decimales ("1.234,56", "24,527,200.00", "59617208,20"); no toma
# cantidades ("1500.000"), cotizaciones ("1391.5000000") ni fechas.
RE_IMPORTE = re.compile(r"(?<![\d.,])(?:\d{1,3}(?:[.,]\d{3})+|\d+)[.,]\d{2}(?![\d.,])")


def detectar_tipo(texto, cfg):
    """El tipo cuyo título aparece primero en el texto (o el tipo por defecto)."""
    encontrados = [(m.start(), t) for t in cfg.tipos.values() if (m := t.titulo.search(texto))]
    if encontrados:
        return min(encontrados, key=lambda x: x[0])[1]
    return cfg.tipos[cfg.tipo_por_defecto]


def valor_campo(tipo_campo, patron, texto, cfg):
    """Valor de un campo según su patrón. Los comprobantes juntan todos los que aparecen
    ('a;b'); el resto se queda con el primero válido (el CUIT, el primero que no es propio)."""
    vistos = []
    for m in patron.finditer(texto):
        v = normalizar(tipo_campo, m.group(1))
        if v is None or (tipo_campo == "cuit" and v in cfg.cuits_propios):
            continue
        if tipo_campo != "comprobante":
            return v
        vistos += [x for x in v.split(";") if x not in vistos]
    return ";".join(vistos) or None


def fecha_de_encabezado(texto_zona):
    """Primera fecha válida (año de 4 dígitos) en la relectura de la zona del número."""
    for m in RE_FECHA.finditer(texto_zona or ""):
        if len(m.group(3)) == 4 and (f := fecha_iso(*m.groups(), permitir_2_digitos=False)):
            return f
    return None


def fecha_suelta(texto, ignorar_tras):
    """Primera fecha válida del texto que no sea, por ejemplo, el vencimiento del CAI."""
    for m in RE_FECHA.finditer(texto):
        antes = texto[max(0, m.start() - 15):m.start()].lower()
        if any(p in antes for p in ignorar_tras):
            continue
        if f := fecha_iso(*m.groups()):
            return f
    return None


def importe_mayor(texto):
    """El importe más grande del documento: en una factura casi siempre es el total."""
    return max((monto(m.group()) for m in RE_IMPORTE.finditer(texto)), default=None)


def decidir(pagina, lecturas_zona, texto_zona):
    """Elige el número del documento combinando dos lecturas independientes:
    - la de la página (candidatos `pagina`, ya sin los números de pedido y citados), y
    - la de la zona del número releída solo con dígitos (más confiable, pesa doble).

    Devuelve (numero, dudoso, alternativas). Una lectura es "dudosa" si las lecturas no
    coinciden, si alguna tiene dígitos de más/menos, o si la zona no dio ningún número.
    """
    votos = Counter()
    for a, b in lecturas_zona:
        if len(b) == 8:
            votos[comprobante(a, b)] += 2
    for a, b in pagina:
        if len(b) == 8:
            votos[comprobante(a, b)] += 1

    crudas = {f"{int(a):05d}-{b}" for a, b in lecturas_zona + pagina}
    if not votos:
        # Ninguna lectura de 8 dígitos. Si hay de 9, lo más común es que una firma o raya
        # pegada al número se haya leído como un dígito extra al final: se trunca.
        for a, b in lecturas_zona + pagina:
            if len(b) == 9:
                votos[comprobante(a, b[:8])] += 1
        if not votos:
            return None, bool(crudas), ";".join(sorted(crudas))
        numero = votos.most_common(1)[0][0]
        return numero, True, ";".join(sorted(crudas - {numero}))

    numero = votos.most_common(1)[0][0]
    alternativas = sorted(crudas - {numero})
    dudoso = bool(alternativas) or (not lecturas_zona and bool(texto_zona))
    return numero, dudoso, ";".join(alternativas)


def extraer(texto, texto_zona="", cfg=None):
    """Datos de un documento: un dict con todos los CAMPOS + 'dudoso' y 'alternativas'."""
    cfg = cfg or config.CFG
    tipo = detectar_tipo(texto, cfg)
    datos = {c.nombre: None for c in CAMPOS}
    datos["tipo"] = tipo.clave
    for nombre, patron in tipo.campos.items():
        datos[nombre] = valor_campo(POR_NOMBRE[nombre].tipo, patron, texto, cfg)

    otros = {x for n in tipo.campos if POR_NOMBRE[n].tipo == "comprobante"
             for x in (datos[n] or "").split(";") if x}
    pagina = [(a, b) for p in tipo.numero for a, b in p.findall(texto)
              if comprobante(a, b) not in otros]
    lecturas = RE_NUM_CRUDO.findall(texto_zona or "")
    datos["numero"], dudoso, datos["alternativas"] = decidir(pagina, lecturas, texto_zona or "")
    datos["dudoso"] = int(dudoso)
    datos["fecha"] = (fecha_de_encabezado(texto_zona) or datos["fecha"]
                      or fecha_suelta(texto, cfg.fechas_a_ignorar_tras))
    # Total sin etiqueta: el importe más grande, solo en PDF digitales (sin zona releída). En
    # un escaneo el total puede estar mal leído y el más grande sería otro (el subtotal).
    if "monto" in tipo.campos and datos["monto"] is None and not texto_zona:
        datos["monto"] = importe_mayor(texto)
    return datos
