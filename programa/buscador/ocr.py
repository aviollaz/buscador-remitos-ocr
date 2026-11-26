"""Lectura de imágenes y PDF con Tesseract, 100% local. Solo lee: los datos se extraen
después del texto (ver extraccion.py)."""

import os

import pytesseract
from PIL import Image, ImageOps

from .config import BASE_DIR, CFG
from .extraccion import SEPARADOR_LECTURAS

OCR = CFG.ocr

# En Windows, buscar Tesseract en las rutas de instalación habituales
if os.name == "nt":
    for _c in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
               r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
               os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")):
        if os.path.exists(_c):
            pytesseract.pytesseract.tesseract_cmd = _c
            break

# Si el idioma viene incluido en ./tessdata, usarlo (no hace falta instalarlo en Tesseract)
_TESSDATA = os.path.join(BASE_DIR, "tessdata")
if os.path.exists(os.path.join(_TESSDATA, f"{OCR['idioma']}.traineddata")):
    os.environ["TESSDATA_PREFIX"] = _TESSDATA

IDIOMA = OCR["idioma"]


def preparar(gris):
    """Normaliza el ancho de la página y sube el contraste."""
    f = OCR["ancho_pagina"] / gris.width
    if f > 1.1 or f < 0.7:
        gris = gris.resize((int(gris.width * f), int(gris.height * f)), Image.LANCZOS)
    return ImageOps.autocontrast(gris)


def leer_zona_numero(gris):
    """Relee la zona donde está impreso el número: recortada, agrandada, con y sin
    binarizar, y aceptando únicamente dígitos, '-' y '/'. Devuelve el texto leído."""
    w, h = gris.size
    x0, y0, x1, y1 = OCR["zona_numero"]
    zona = gris.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    ancho = OCR["ancho_zona"]
    alto = max(1, int(zona.height * ancho / zona.width))
    zona = ImageOps.autocontrast(zona.resize((ancho, alto), Image.LANCZOS))

    textos = []
    for umbral in (None, 160):
        z = zona if umbral is None else zona.point(lambda px: 255 if px > umbral else 0)
        textos.append(pytesseract.image_to_string(
            z, lang=IDIOMA, config="--psm 6 -c tessedit_char_whitelist=0123456789-/"))
    return SEPARADOR_LECTURAS.join(textos)


def leer_imagen(img, paso=None):
    """OCR de la página + relectura de la zona del número. Devuelve (texto, texto_zona).
    paso=1: solo el encabezado (rápido); paso=2: solo la página completa."""
    gris = ImageOps.exif_transpose(img).convert("L")
    pagina = gris
    if paso == 1:
        pagina = gris.crop((0, 0, gris.width, int(gris.height * OCR["alto_encabezado"])))
    texto = pytesseract.image_to_string(preparar(pagina), lang=IDIOMA, config="--psm 3")
    if paso == 2:
        return texto, ""
    return texto, leer_zona_numero(gris)


def es_escaneo(pagina):
    """True si la página del PDF es básicamente una imagen (escaneo o foto)."""
    area = abs(pagina.rect)
    for img in pagina.get_images(full=True):
        for r in pagina.get_image_rects(img[0]):
            if abs(r) >= 0.5 * area:
                return True
    return False


def paginas_pdf(ruta, paso=None):
    """PDF digital: se usa su texto (exacto). PDF escaneado: se ignora la "capa de texto"
    que agregan muchos escáneres/apps (suele ser mala) y se hace OCR propio.
    Devuelve por página (texto, texto_zona, se_uso_ocr)."""
    import pymupdf
    with pymupdf.open(ruta) as doc:
        for pagina in doc:
            t = pagina.get_text().strip()
            if not es_escaneo(pagina) and len(t) >= 30:
                yield t, "", False
            else:
                pix = pagina.get_pixmap(dpi=OCR["dpi_pdf"], colorspace=pymupdf.csGRAY)
                img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
                yield *leer_imagen(img, paso), True


def procesar(ruta, paso=None):
    """Lee un archivo. Devuelve (ruta, texto, texto_zona, completo, error) (paso: ver
    leer_imagen). `completo`: ya se leyó la página entera; en el paso 1 solo pasa con los
    PDF digitales (sin OCR), que así no se vuelven a leer en el paso 2.
    Corre en procesos separados (multiprocessing), por eso nunca lanza excepciones."""
    try:
        if ruta.lower().endswith(".pdf"):
            partes = list(paginas_pdf(ruta, paso))
        else:
            with Image.open(ruta) as im:
                partes = [(*leer_imagen(im, paso), True)]
        texto = "\n".join(p[0] for p in partes)
        texto_zona = SEPARADOR_LECTURAS.join(p[1] for p in partes if p[1])
        completo = paso != 1 or not any(p[2] for p in partes)
        return ruta, texto, texto_zona, completo, None
    except Exception as e:  # noqa: BLE001 - se informa por archivo y se sigue con el resto
        return ruta, "", "", False, str(e)
