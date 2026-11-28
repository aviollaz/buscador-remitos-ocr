"""Generador de remitos SINTÉTICOS para tests, demo y evaluación.

Todos los datos (empresa, clientes, CUIT, números) son inventados. Las imágenes imitan un
escaneo A4 a 300 dpi con defectos reales: leve rotación, desenfoque, tinta gastada,
manchas, compresión JPEG, sellos y, opcionalmente, una raya de birome tapando un dígito
del número (el caso más difícil que aparece en la práctica).

Uso:
    python tests/muestras.py carpeta_destino --cantidad 50 [--semilla 1] [--ocluidos 0.1]
Genera las imágenes y un `verdad.json` con los datos correctos de cada una.
"""

import argparse
import json
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ANCHO, ALTO = 2480, 3508           # A4 a 300 dpi

_FUENTES = {
    False: ["LiberationSans-Regular.ttf", "arial.ttf", "Arial.ttf", "DejaVuSans.ttf"],
    True: ["LiberationSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"],
}
_DIRS = ["/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype/dejavu",
         "/Library/Fonts", "/System/Library/Fonts/Supplemental", r"C:\Windows\Fonts"]

CLIENTES = ["DISTRIBUIDORA EL ALFAJOR SRL", "PANIFICADORA LOS ANDES SA",
            "SUPERMERCADOS DEL SUR SA", "HELADOS LA ESQUINA SRL", "CONFITERIA BELGRANO SA",
            "MAYORISTA RUTA 5 SRL", "ALMACEN DON PEDRO SA", "LOGISTICA PAMPA SRL",
            "PASTELERIA DULCE HOGAR SA", "COOPERATIVA LACTEA UNION LTDA"]
PRODUCTOS = ["DULCE DE LECHE PASTELERO X 10 KG", "DULCE DE LECHE CLASICO X 400 GR",
             "LECHE EN POLVO ENTERA X 25 KG", "QUESO CREMOSO X 4 KG", "MOZZARELLA X 3 KG",
             "CREMA DE LECHE X 5 LT", "MANTECA X 200 GR", "QUESO PORT SALUT X 400 GR"]


def fuente(tam, negrita=False):
    for nombre in _FUENTES[negrita]:
        for d in _DIRS:
            p = os.path.join(d, nombre)
            if os.path.exists(p):
                return ImageFont.truetype(p, tam)
    return ImageFont.load_default(size=tam)


def datos_aleatorios(rng, numero=None):
    pv = 7
    numero = numero if numero is not None else rng.randint(40000, 49999)
    pedido = numero + rng.randint(2500, 4000)
    d, m, a = rng.randint(1, 28), rng.randint(1, 12), rng.choice([2025, 2026])
    return {
        "remito": f"{pv:05d}-{numero:08d}",
        "pedido": f"{pv:05d}-{pedido:08d}",
        "fecha": f"{d:02d}/{m:02d}/{a}",
        "cliente": rng.choice(CLIENTES),
        "codigo_cliente": f"{rng.randint(1, 89999):06d}",
        "cuit": f"30-{rng.randint(50000000, 79999999)}-{rng.randint(0, 9)}",
        "items": [(rng.choice(PRODUCTOS), rng.randint(1, 900)) for _ in range(rng.randint(1, 6))],
        "copia": rng.choice(["ORIGINAL", "DUPLICADO"]),
    }


def dibujar(d, rng, ocluir=False):
    """Dibuja el remito y devuelve una imagen en escala de grises."""
    img = Image.new("L", (ANCHO, ALTO), 255)
    g = ImageDraw.Draw(img)
    tinta = rng.randint(0, 60)                   # tinta negra o algo gastada
    f40, f40b = fuente(40), fuente(40, True)
    f32 = fuente(32)

    # Marco y divisiones
    x0, x1 = 70, ANCHO - 70
    g.rectangle([x0, 100, x1, 3150], outline=tinta, width=4)
    g.line([1240, 230, 1240, 700], fill=tinta, width=3)
    for y in (700, 1070, 1160, 1380, 1460, 2950):
        g.line([x0, y, x1, y], fill=tinta, width=3)

    # Encabezado izquierdo (empresa ficticia)
    g.text((200, 230), "LÁCTEOS EJEMPLO", font=fuente(78, True), fill=tinta)
    g.text((330, 420), "Lácteos del Ejemplo S.A.", font=f40, fill=tinta)
    g.text((240, 500), "Planta: Ruta 99 Km 12 (B1234XYZ)", font=f40, fill=tinta)
    g.text((240, 560), "Tel.: (011) 4000-0000", font=f40, fill=tinta)
    g.text((300, 620), "I.V.A. Responsable Inscripto", font=f40b, fill=tinta)

    # Encabezado derecho: tipo, número, fecha
    g.rectangle([1080, 120, 1200, 230], outline=tinta, width=4)
    g.text((1110, 128), "R", font=fuente(80, True), fill=tinta)
    g.text((1050, 250), "Código N°: 91", font=fuente(30, True), fill=tinta)
    g.text((1560, 160), "REMITO", font=fuente(90, True), fill=tinta)
    pv, num = d["remito"].split("-")
    texto_num = f"{pv} - {num}"
    g.text((1400, 290), texto_num, font=fuente(88, True), fill=tinta)
    caja_num = g.textbbox((1400, 290), texto_num, font=fuente(88, True))
    ancho_digito = g.textlength("0", font=fuente(88, True))
    g.text((1500, 430), f"Fecha:   {d['fecha']}", font=fuente(46, True), fill=tinta)
    g.text((1600, 505), d["copia"], font=fuente(46, True), fill=tinta)
    g.text((1300, 590), "C.U.I.T: 30-12345678-9", font=f32, fill=tinta)
    g.text((1300, 630), "Inicio de Actividades: 01/10/1990", font=f32, fill=tinta)

    # Cliente
    g.text((110, 790), f"Sr/res:  {d['cliente']}", font=f40b, fill=tinta)
    g.text((1300, 790), f"Cliente:   {d['codigo_cliente']}", font=f40b, fill=tinta)
    g.text((110, 860), "Domicilio:  CALLE FALSA 123", font=f40, fill=tinta)
    g.text((110, 930), "IVA:  Responsable Inscripto", font=f40, fill=tinta)
    g.text((1300, 930), f"C.U.I.T.   {d['cuit']}", font=f40, fill=tinta)
    g.text((110, 1100), "Horario de Recepción:", font=f40b, fill=tinta)

    # Pedido (número con el mismo formato que el remito: no hay que confundirlos)
    ppv, pnum = d["pedido"].split("-")
    g.text((110, 1220), "Bultos :", font=f40b, fill=tinta)
    g.text((1300, 1220), f"Pedido N° :  PEDV  -  {ppv}  - {pnum}", font=f40b, fill=tinta)
    g.text((1300, 1290), f"OC N° : {rng.randint(100000, 999999)}", font=f40, fill=tinta)

    # Ítems
    g.text((150, 1400), "Artículo     Cantidad   Descripción", font=f40b, fill=tinta)
    y = 1500
    for prod, cant in d["items"]:
        g.text((150, y), f"ART-{rng.randint(1000, 9999)}", font=f40, fill=tinta)
        g.text((480, y), f"{cant},00", font=f40, fill=tinta)
        g.text((720, y), prod, font=f40, fill=tinta)
        y += 70

    # Pie (fecha de vencimiento del CAI: no hay que tomarla como fecha del remito)
    g.text((110, 3000), "Se hace entrega de la mercadería en perfecto estado.", font=f32,
           fill=tinta)
    g.text((110, 3250), "Código de operación de traslado:  " + "".join(
        rng.choice("0123456789abcdef") for _ in range(32)), font=f32, fill=tinta)
    g.text((1600, 3230), f"C.A.I. N°:  {rng.randint(10**13, 10**14 - 1)}", font=f32, fill=tinta)
    g.text((1600, 3280), "Fecha vto:  30/09/2026", font=f32, fill=tinta)

    # Sello de recepción (ruido típico)
    if rng.random() < 0.6:
        sello = Image.new("L", (700, 300), 255)
        gs = ImageDraw.Draw(sello)
        gs.rectangle([5, 5, 695, 295], outline=90, width=6)
        gs.text((60, 40), "RECIBIDO A CONTROLAR", font=fuente(50), fill=90)
        gs.text((180, 150), f"{rng.randint(1, 28)} ABR 2026", font=fuente(60), fill=90)
        sello = sello.rotate(rng.uniform(-15, 15), expand=True, fillcolor=255)
        img.paste(Image.composite(sello, img.crop((1500, 2500, 1500 + sello.width,
                                                   2500 + sello.height)),
                                  sello.point(lambda p: 255 if p < 200 else 0)), (1500, 2500))

    # Raya de birome tapando el último dígito del número
    if ocluir:
        l, t, r, b = caja_num
        xd = r - ancho_digito                     # el último dígito
        g.line([xd - 25, t - 15, r + 30, b + 20], fill=20, width=14)
        g.line([xd - 35, (t + b) // 2 + 8, r + 40, (t + b) // 2 - 6], fill=20, width=11)

    return img


def degradar(img, rng, calidad):
    """Simula un escaneo real. calidad: 'buena' | 'regular' | 'mala'."""
    img = img.rotate(rng.uniform(-1.2, 1.2), resample=Image.BICUBIC, fillcolor=255)
    if calidad == "mala":                         # escáner a ~150 dpi, tinta gastada
        f = rng.uniform(0.38, 0.5)
        img = img.resize((int(ANCHO * f), int(ALTO * f)), Image.BILINEAR)
        img = img.resize((ANCHO, ALTO), Image.BILINEAR)
        img = img.point(lambda p: min(255, int(p * 0.55 + 105)))
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(1.2, 2.2)))
    elif calidad == "regular":
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.8, 1.5)))
    else:
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.0, 0.6)))
    px = img.load()
    for _ in range(rng.randint(500, 6000)):      # motas de suciedad
        x, y = rng.randrange(ANCHO), rng.randrange(ALTO)
        px[x, y] = rng.randint(0, 120)
    return img


def generar(destino, cantidad, semilla=1, ocluidos=0.1, calidades=(0.5, 0.3, 0.2)):
    rng = random.Random(semilla)
    os.makedirs(destino, exist_ok=True)
    verdad = {}
    numeros = rng.sample(range(40000, 50000), cantidad)   # números de remito únicos
    for i in range(cantidad):
        d = datos_aleatorios(rng, numeros[i])
        ocluir = rng.random() < ocluidos
        calidad = rng.choices(["buena", "regular", "mala"], weights=calidades)[0]
        img = degradar(dibujar(d, rng, ocluir), rng, calidad)
        nombre = f"scan_{i:04d}.jpg"                 # el nombre NO dice qué remito es
        img.save(os.path.join(destino, nombre),
                 quality=rng.randint(30, 55) if calidad == "mala" else rng.randint(55, 90))
        verdad[nombre] = {k: d[k] for k in ("remito", "pedido", "fecha", "cliente")}
        verdad[nombre].update(ocluido=ocluir, calidad=calidad)
    with open(os.path.join(destino, "verdad.json"), "w", encoding="utf-8") as f:
        json.dump(verdad, f, ensure_ascii=False, indent=1)
    return verdad


def generar_factura_pdf(ruta, numero, citados, cliente, fecha, monto, cod_cliente="029257"):
    """Factura electrónica SINTÉTICA en PDF digital (con texto, sin escanear), con el formato
    de config.toml. `cliente`: el proveedor; `citados`: números de remito que cubre."""
    import pymupdf

    pv, n = numero.split("-")
    lineas = ["FACTURA", "A   Cod. 01", "LÁCTEOS EJEMPLO S.A.",
              f"Punto de Venta: {pv}   Comp. Nro: {n}", f"Fecha de Emisión: {fecha}",
              "CUIT: 30-12345678-9   Ingresos Brutos: 901-000000",
              "Razón Social:", cliente,
              "Condición frente al IVA: IVA Responsable Inscripto",
              f"Código de Cliente: {cod_cliente}", f"Remitos: {', '.join(citados)}",
              "Producto / Servicio   Cantidad   Precio Unit.   Subtotal",
              "DULCE DE LECHE CLASICO X 400 GR   100   1.000,00   100.000,00",
              f"Importe Total: $ {monto}", "CAE N°: 75123456789012   Fecha de Vto. de CAE: 25/03/2026"]
    doc = pymupdf.open()
    pagina = doc.new_page()
    for i, linea in enumerate(lineas):
        pagina.insert_text((60, 70 + 20 * i), linea, fontsize=11)
    doc.save(ruta)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("destino")
    ap.add_argument("--cantidad", type=int, default=20)
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--ocluidos", type=float, default=0.1)
    a = ap.parse_args()
    generar(a.destino, a.cantidad, a.semilla, a.ocluidos)
    print(f"{a.cantidad} remitos sintéticos en {a.destino}")
