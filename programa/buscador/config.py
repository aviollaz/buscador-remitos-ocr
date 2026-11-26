"""Rutas y configuración. Todo se guarda al lado del programa, nunca en la nube."""

import os
import tomllib

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Índice SQLite (se puede cambiar con la variable de entorno REMITOS_DB, útil para tests)
DB = os.environ.get("REMITOS_DB", os.path.join(BASE_DIR, "remitos.db"))

# Carpeta donde se generan los Excel de resultados y las copias de archivos: "Resultados",
# al lado de la carpeta del programa, para que sea fácil de encontrar
SALIDAS = os.environ.get("REMITOS_SALIDAS",
                         os.path.join(os.path.dirname(BASE_DIR), "Resultados"))

EXTS = {".jpg", ".jpeg", ".jfif", ".jpe", ".png", ".tif", ".tiff", ".bmp", ".webp", ".gif",
        ".pdf"}

_DEFAULTS = {
    "documento": {
        "palabras_pedido": ["Pedido"],
        "etiqueta_cliente": r"S\S{0,2}r?es",
        "fin_cliente": r"C\w{0,3}nte",
        "zona_numero": [0.45, 0.0, 1.0, 0.16],
    },
    "ocr": {"idioma": "spa", "ancho_pagina": 2000, "ancho_zona": 1400, "dpi_pdf": 300,
            "alto_encabezado": 0.45},
}


def _cargar():
    cfg = {k: dict(v) for k, v in _DEFAULTS.items()}
    ruta = os.environ.get("REMITOS_CONFIG", os.path.join(BASE_DIR, "config.toml"))
    if os.path.exists(ruta):
        with open(ruta, "rb") as f:
            for seccion, valores in tomllib.load(f).items():
                cfg.setdefault(seccion, {}).update(valores)
    return cfg


CFG = _cargar()
DOC = CFG["documento"]
OCR = CFG["ocr"]
