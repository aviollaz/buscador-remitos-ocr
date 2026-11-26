"""Rutas y configuración. Todo se guarda al lado del programa, nunca en la nube.

config.toml es la única fuente de la configuración (este módulo no tiene valores propios):
se valida al cargar y cualquier error se informa con la sección y la clave."""

import hashlib
import json
import os
import re
import tomllib
from dataclasses import dataclass

from . import campos

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Índice SQLite (se puede cambiar con la variable de entorno BUSCADOR_DB, útil para tests)
DB_POR_DEFECTO = os.path.join(BASE_DIR, "indice.db")
DB_VIEJA = os.path.join(BASE_DIR, "remitos.db")          # nombre hasta la versión 2
DB = os.environ.get("BUSCADOR_DB", DB_POR_DEFECTO)

# Excel de resultados y copias de archivos: "Resultados", al lado de la carpeta del programa
SALIDAS = os.environ.get("BUSCADOR_SALIDAS",
                         os.path.join(os.path.dirname(BASE_DIR), "Resultados"))

RUTA = os.environ.get("BUSCADOR_CONFIG", os.path.join(BASE_DIR, "config.toml"))

EXTS = {".jpg", ".jpeg", ".jfif", ".jpe", ".png", ".tif", ".tiff", ".bmp", ".webp", ".gif",
        ".pdf"}


class ErrorConfig(Exception):
    pass


@dataclass(frozen=True)
class TipoDoc:
    clave: str                   # "remito", "factura"...
    nombre: str                  # "Remito"
    titulo: re.Pattern           # identifica el tipo en el texto
    numero: list                 # patrones con 2 grupos: punto de venta y número
    campos: dict                 # campo -> patrón con 1 grupo


@dataclass(frozen=True)
class Config:
    ocr: dict
    tipos: dict                  # clave -> TipoDoc, en el orden de config.toml
    tipo_por_defecto: str
    cuits_propios: frozenset
    fechas_a_ignorar_tras: tuple
    huella: str                  # cambia si cambia la forma de extraer los datos


def _regex(patron, donde, grupos):
    if not isinstance(patron, str):
        raise ErrorConfig(f"{donde}: tiene que ser un texto entre comillas")
    try:
        r = re.compile(patron, re.I)
    except re.error as e:
        raise ErrorConfig(f"{donde}: expresión regular inválida ({e})") from None
    if r.groups != grupos:
        raise ErrorConfig(f"{donde}: tiene que tener {grupos} grupo(s) entre paréntesis "
                          f"y tiene {r.groups}")
    return r


def _pedir(d, clave, donde):
    if clave not in d:
        raise ErrorConfig(f"{donde}: falta '{clave}'")
    return d[clave]


def compilar(datos):
    """Valida el contenido de config.toml y devuelve la configuración lista para usar."""
    general = _pedir(datos, "general", "config.toml")
    ocr = _pedir(datos, "ocr", "config.toml")
    tipos_toml = _pedir(datos, "tipos", "config.toml")
    if not tipos_toml:
        raise ErrorConfig("[tipos]: tiene que haber al menos un tipo de documento")

    tipos = {}
    for clave, t in tipos_toml.items():
        donde = f"[tipos.{clave}]"
        numero = _pedir(t, "numero", donde)
        if isinstance(numero, str):
            numero = [numero]
        cmp = {}
        for nombre, patron in t.get("campos", {}).items():
            if nombre not in campos.EXTRAIBLES:
                raise ErrorConfig(f"[tipos.{clave}.campos] {nombre}: no es un campo conocido "
                                  f"(se puede usar: {', '.join(campos.EXTRAIBLES)})")
            cmp[nombre] = _regex(patron, f"[tipos.{clave}.campos] {nombre}", 1)
        tipos[clave] = TipoDoc(
            clave=clave, nombre=_pedir(t, "nombre", donde),
            titulo=_regex(_pedir(t, "titulo", donde), f"{donde} titulo", 0),
            numero=[_regex(p, f"{donde} numero", 2) for p in numero],
            campos=cmp)

    defecto = _pedir(general, "tipo_por_defecto", "[general]")
    if defecto not in tipos:
        raise ErrorConfig(f"[general] tipo_por_defecto: '{defecto}' no está en [tipos]")
    for clave in ("idioma", "ancho_pagina", "ancho_zona", "dpi_pdf", "alto_encabezado",
                  "zona_numero"):
        _pedir(ocr, clave, "[ocr]")

    huella = hashlib.sha256(json.dumps(
        {"general": general, "tipos": tipos_toml}, sort_keys=True).encode()).hexdigest()
    return Config(
        ocr=ocr, tipos=tipos, tipo_por_defecto=defecto,
        cuits_propios=frozenset(campos.normalizar("cuit", c)
                                for c in general.get("cuits_propios", [])),
        fechas_a_ignorar_tras=tuple(p.lower() for p in general.get("fechas_a_ignorar_tras", [])),
        huella=huella)


def cargar(ruta=RUTA):
    if not os.path.exists(ruta):
        raise ErrorConfig(f"No encontré el archivo de configuración: {ruta}")
    try:
        with open(ruta, "rb") as f:
            datos = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ErrorConfig(f"config.toml tiene un error de formato: {e}") from None
    return compilar(datos)


def __getattr__(nombre):
    """config.CFG se carga la primera vez que se usa (no al importar): así un error en
    config.toml se informa con un mensaje claro y no con una traza al arrancar."""
    if nombre == "CFG":
        global CFG
        CFG = cargar()
        return CFG
    raise AttributeError(nombre)
