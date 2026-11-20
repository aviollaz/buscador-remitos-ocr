"""Lectura de imágenes y PDF con Tesseract, 100% local."""

import os

import pytesseract
from PIL import Image, ImageOps

from .config import BASE_DIR, DOC, OCR
from .extraccion import RE_NUM_CRUDO, decidir, extraer, fecha_de_encabezado

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
    """Relee la zona donde está impreso el número de remito: recortada, agrandada,
    con y sin binarizar, y aceptando únicamente dígitos, '-' y '/'.
    Devuelve (lecturas [(pv, numero)], texto)."""
    w, h = gris.size
    x0, y0, x1, y1 = DOC["zona_numero"]
    zona = gris.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    ancho = OCR["ancho_zona"]
    alto = max(1, int(zona.height * ancho / zona.width))
    zona = ImageOps.autocontrast(zona.resize((ancho, alto), Image.LANCZOS))

    lecturas, textos = [], []
    for umbral in (None, 160):
        z = zona if umbral is None else zona.point(lambda px: 255 if px > umbral else 0)
        t = pytesseract.image_to_string(
            z, lang=IDIOMA, config="--psm 6 -c tessedit_char_whitelist=0123456789-/")
        textos.append(t)
        lecturas += RE_NUM_CRUDO.findall(t)
    return lecturas, "\n".join(textos)


def leer_imagen(img):
    """OCR de la página completa + relectura de la zona del número.
    Devuelve (texto, lecturas_zona, texto_zona)."""
    gris = ImageOps.exif_transpose(img).convert("L")
    texto = pytesseract.image_to_string(preparar(gris), lang=IDIOMA, config="--psm 3")
    lecturas, texto_zona = leer_zona_numero(gris)
    return texto, lecturas, texto_zona


def es_escaneo(pagina):
    """True si la página del PDF es básicamente una imagen (escaneo o foto)."""
    area = abs(pagina.rect)
    for img in pagina.get_images(full=True):
        for r in pagina.get_image_rects(img[0]):
            if abs(r) >= 0.5 * area:
                return True
    return False


def paginas_pdf(ruta):
    """PDF digital: se usa su texto (exacto). PDF escaneado: se ignora la "capa de texto"
    que agregan muchos escáneres/apps (suele ser mala) y se hace OCR propio."""
    import pymupdf
    with pymupdf.open(ruta) as doc:
        for pagina in doc:
            t = pagina.get_text().strip()
            if not es_escaneo(pagina) and len(t) >= 30:
                yield t, [], ""
            else:
                pix = pagina.get_pixmap(dpi=OCR["dpi_pdf"], colorspace=pymupdf.csGRAY)
                yield leer_imagen(Image.frombytes("L", (pix.width, pix.height), pix.samples))


def procesar(ruta):
    """Lee un archivo y devuelve una fila lista para el índice.
    Corre en procesos separados (multiprocessing), por eso nunca lanza excepciones."""
    try:
        if ruta.lower().endswith(".pdf"):
            partes = list(paginas_pdf(ruta))
        else:
            with Image.open(ruta) as im:
                partes = [leer_imagen(im)]
        texto = "\n".join(p[0] for p in partes)
        lecturas = [x for p in partes for x in p[1]]
        texto_zona = "\n".join(p[2] for p in partes)

        _, pedido, fecha, cliente = extraer(texto)
        remito, dudoso, alternativas = decidir(texto, lecturas, texto_zona)
        fecha = fecha_de_encabezado(texto_zona) or fecha
        return (ruta, texto, remito, pedido, fecha, cliente, int(dudoso), alternativas, None)
    except Exception as e:  # noqa: BLE001 - se informa por archivo y se sigue con el resto
        return (ruta, "", "", "", "", "", 0, "", str(e))
