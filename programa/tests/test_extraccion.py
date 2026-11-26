import re

import pytest

from buscador.config import ErrorConfig, cargar, compilar
from buscador.extraccion import SEPARADOR_LECTURAS, decidir, extraer, fecha_de_encabezado

REMITO = """REMITO
00007 - 00043300
Lácteos del Ejemplo S.A. Fecha: 25/11/2025
C.U.I.T: 30-58661152-2
Inicio de Actividades: 01/10/1990
Sr/res: SUPERMERCADOS DEL SUR SA Cliente: 001234
C.U.I.T. 30-71162133-0
Bultos: Turno 10-03 Pedido N°: PEDV - 00007 - 00046905
Se hace entrega... En su defecto serán facturados a Uds.
Fecha vto: 30/09/2026
"""

# Formato provisorio de factura (el de config.toml) que además cita sus remitos
FACTURA = """FACTURA
A
Punto de Venta: 00002   Comp. Nro: 00000123
Fecha de Emisión: 15/03/2026
CUIT: 30-58661152-2
Apellido y Nombre / Razón Social: HELADOS LA ESQUINA SRL
CUIT: 30-71162133-0
Código de Cliente: 029257
Remitos: 0007-00043300, 0007-00043301
Importe Total: $ 1.234.567,89
"""


def test_remito_numero_pedido_y_cliente():
    d = extraer(REMITO)
    assert d["tipo"] == "remito"
    assert d["numero"] == "00007-00043300"
    assert d["pedido"] == "00007-00046905"
    assert d["cliente"] == "SUPERMERCADOS DEL SUR SA"
    assert d["cod_cliente"] == "1234"
    assert d["cuit"] == "30-71162133-0"           # el de la empresa (propio) se ignora
    assert d["monto"] is None                      # los remitos no tienen monto


def test_fecha_ignora_inicio_de_actividades_y_vencimiento_cai():
    assert extraer(REMITO)["fecha"] == "2025-11-25"
    texto = "REMITO\nInicio de Actividades: 01/10/1990\nFecha vto: 30/09/2026\nentrega 03/02/2026"
    assert extraer(texto)["fecha"] == "2026-02-03"


def test_cliente_tolera_errores_de_ocr_en_la_etiqueta():
    assert extraer("Sríres: DISTRIBUIDORA NORTE SRL  Clente: 12")["cliente"] == \
        "DISTRIBUIDORA NORTE SRL"


def test_factura_provisoria():
    d = extraer(FACTURA)
    assert d["tipo"] == "factura"
    assert d["numero"] == "00002-00000123"          # los remitos citados no son el número
    assert d["citados"] == "00007-00043300;00007-00043301"
    assert d["fecha"] == "2026-03-15"
    assert d["cliente"] == "HELADOS LA ESQUINA SRL"
    assert d["cuit"] == "30-71162133-0"
    assert d["cod_cliente"] == "29257"
    assert d["monto"] == 1234567.89
    assert not d["dudoso"]


def test_tipo_lo_decide_el_titulo_que_aparece_primero():
    assert extraer(REMITO)["tipo"] == "remito"            # "facturados" no es "FACTURA"
    assert extraer("FACTURA B\nRemito N° 0007-00043300")["tipo"] == "factura"
    assert extraer("sin título 0007-00043300")["tipo"] == "remito"   # tipo por defecto


def test_factura_que_no_coincide_con_el_formato_no_rompe_nada():
    d = extraer("FACTURA\nalgo que no se parece a nada")
    assert d["tipo"] == "factura" and d["numero"] is None and d["monto"] is None


def test_fecha_de_encabezado_descarta_anios_imposibles():
    assert fecha_de_encabezado("00007-00041286\n22/07/2098\n01/10/1990") is None
    assert fecha_de_encabezado("00007-00041286\n22/07/2025") == "2025-07-22"


def test_las_lecturas_de_la_zona_no_se_pegan_entre_si():
    # Lectura 1 termina con la fecha, lectura 2 empieza con el número: "2026 -\n#\n00007"
    # no es un número de remito (antes marcaba como dudosos remitos bien leídos).
    zona = SEPARADOR_LECTURAS.join(["00007 - 00041144\n10/04/2026 -", "00007 - 00041144"])
    d = extraer("REMITO\n00007 - 00041144", zona)
    assert d["numero"] == "00007-00041144" and not d["dudoso"]


def test_decidir_la_zona_del_numero_pesa_mas_que_la_pagina():
    # La página leyó un 5 como 9; la zona (solo dígitos) lo leyó bien dos veces.
    zona = [("00007", "00046355"), ("00007", "00046355")]
    numero, dudoso, alternativas = decidir([("00007", "00046395")], zona, "00007-00046355")
    assert numero == "00007-00046355"
    assert dudoso and alternativas == "00007-00046395"


def test_decidir_lectura_coherente_no_es_dudosa():
    zona = [("00007", "00043300"), ("00007", "00043300")]
    assert decidir([("00007", "00043300")], zona, "x") == ("00007-00043300", False, "")


def test_decidir_digito_de_menos_queda_dudoso_sin_inventar_numero():
    zona = [("00007", "0004604"), ("00007", "0004604")]
    numero, dudoso, alternativas = decidir([("00007", "0004604")], zona, "x")
    assert numero is None and dudoso and alternativas == "00007-0004604"


def test_decidir_digito_extra_al_final_se_trunca():
    # Una raya pegada al número suele leerse como un dígito más al final.
    numero, dudoso, _ = decidir([], [("00007", "000489987")], "00007-000489987")
    assert numero == "00007-00048998" and dudoso


# ---------------------------------------------------------------- configuración

def _config(**cambios):
    base = {
        "general": {"tipo_por_defecto": "remito"},
        "ocr": {k: 1 for k in ("idioma", "ancho_pagina", "ancho_zona", "dpi_pdf",
                               "alto_encabezado", "zona_numero")},
        "tipos": {"remito": {"nombre": "Remito", "titulo": "REMITO",
                             "numero": [r"(\d{4,5})-(\d{8})"],
                             "campos": {"cliente": r"Cliente: (.+)"}}},
    }
    for ruta, valor in cambios.items():
        d = base
        *camino, ultima = ruta.split("__")
        for k in camino:
            d = d[k]
        d[ultima] = valor
    return base


@pytest.mark.parametrize("cambios, mensaje", [
    ({"tipos__remito__campos": {"importe": "(x)"}}, "importe: no es un campo conocido"),
    ({"tipos__remito__campos": {"cliente": "(x"}}, "[tipos.remito.campos] cliente"),
    ({"tipos__remito__campos": {"cliente": "sin grupo"}}, "1 grupo(s)"),
    ({"tipos__remito__numero": [r"(\d+)"]}, "numero: tiene que tener 2 grupo(s)"),
    ({"general__tipo_por_defecto": "factura"}, "tipo_por_defecto"),
])
def test_config_invalida_dice_donde_esta_el_error(cambios, mensaje):
    with pytest.raises(ErrorConfig, match=re.escape(mensaje)):
        compilar(_config(**cambios))


def test_config_del_repositorio_es_valida_y_la_huella_cambia_con_los_tipos():
    assert {"remito", "factura"} <= set(cargar().tipos)
    a = compilar(_config()).huella
    b = compilar(_config(tipos__remito__campos={"cliente": r"Sr/res: (.+)"})).huella
    assert a != b
