"""Fuente única de verdad de los datos que se guardan de cada documento.

De CAMPOS salen las columnas del índice, la extracción, los filtros, la tabla de la
ventana y las columnas del Excel. Para agregar un dato nuevo alcanza con sumarlo acá (y su
expresión regular en config.toml)."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Campo:
    nombre: str                  # columna en el índice y clave en config.toml
    etiqueta: str                # cómo se muestra
    tipo: str                    # texto | comprobante | fecha | codigo | cuit | monto
    ancho: int                   # ancho de columna en el Excel (caracteres)
    buscar_por_numero: bool = False   # al buscar un número, también se mira este campo


CAMPOS = [
    Campo("tipo", "Tipo", "texto", 10),
    Campo("numero", "Número", "comprobante", 18),
    Campo("fecha", "Fecha", "fecha", 12),
    Campo("cliente", "Cliente", "texto", 35),
    Campo("cod_cliente", "Cód. cliente", "codigo", 12),
    Campo("cuit", "CUIT", "cuit", 15),
    Campo("pedido", "Pedido", "comprobante", 18, buscar_por_numero=True),
    Campo("citados", "Comprobantes citados", "comprobante", 30),
    Campo("monto", "Monto", "monto", 14),
]
POR_NOMBRE = {c.nombre: c for c in CAMPOS}
# Campos que se leen con una expresión regular de config.toml ("tipo" y "numero" tienen
# su propia lógica: título del documento y votación entre lecturas).
EXTRAIBLES = [c.nombre for c in CAMPOS if c.nombre not in ("tipo", "numero")]

RE_COMPROBANTE = re.compile(r"(?<!\d)(\d{1,5})\s*[-–—]\s*(\d{1,8})(?!\d)")
RE_FECHA = re.compile(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{2,4})(?!\d)")
ANIO_MAX = date.today().year + 1


def comprobante(pv, n):
    """Punto de venta + número → PPPPP-NNNNNNNN."""
    return f"{int(pv):05d}-{int(n):08d}"


def fecha_iso(d, m, y, permitir_2_digitos=True):
    """dd, mm, aaaa (o aa) → aaaa-mm-dd, o None si la fecha no es válida."""
    d, m, y = int(d), int(m), int(y)
    if y < 100:
        if not permitir_2_digitos:
            return None
        y += 2000
    if not (2000 <= y <= ANIO_MAX):
        return None
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def monto(texto):
    """'1.234,56' / '1234,56' / '1,234.56' / '1234.56' → float. Sin separador decimal claro,
    el punto se toma como separador de miles (formato argentino)."""
    t = re.sub(r"[^\d.,]", "", texto)
    if not re.search(r"\d", t):
        return None
    if "," in t and "." in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
    elif "," in t:
        dec = ","
    else:
        dec = "." if re.search(r"\.\d{1,2}$", t) else ""
    miles = "." if dec == "," else ","
    t = t.replace(miles, "")
    if dec == ",":
        t = t.replace(",", ".")
    elif dec == "":
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def normalizar(tipo, crudo):
    """Convierte lo leído al formato guardado en el índice. None si no hay un valor válido."""
    if crudo is None:
        return None
    crudo = str(crudo)
    if tipo == "comprobante":
        nums = list(dict.fromkeys(comprobante(*m.groups()) for m in RE_COMPROBANTE.finditer(crudo)))
        return ";".join(nums) or None
    if tipo == "fecha":
        m = RE_FECHA.search(crudo.replace("-", "/"))     # también "16-07-26"
        return fecha_iso(*m.groups()) if m else None
    if tipo == "codigo":
        dig = re.sub(r"\D", "", crudo)
        return str(int(dig)) if dig else None
    if tipo == "cuit":
        dig = re.sub(r"\D", "", crudo)
        return f"{dig[:2]}-{dig[2:10]}-{dig[10]}" if len(dig) == 11 else None
    if tipo == "monto":
        return monto(crudo)
    return crudo.strip(" :;.-\t") or None


def mostrar(tipo, valor):
    """Valor del índice → texto para mostrar."""
    if valor is None or valor == "":
        return ""
    if tipo == "fecha":
        y, m, d = valor.split("-")
        return f"{d}/{m}/{y}"
    if tipo == "monto":
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(valor)


def plano(texto):
    """Minúsculas y sin acentos, para comparar nombres escritos de distintas formas."""
    if texto is None:
        return None
    t = unicodedata.normalize("NFKD", str(texto).lower())
    return "".join(c for c in t if not unicodedata.combining(c))
