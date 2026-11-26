from remitos.extraccion import decidir, extraer, fecha_de_encabezado

PAGINA = """REMITO
00007 - 00043300
Lácteos del Ejemplo S.A. Fecha: 25/11/2025
Inicio de Actividades: 01/10/1990
Sr/res: SUPERMERCADOS DEL SUR SA Cliente: 1234
Bultos: Turno 10-03 Pedido N°: PEDV - 00007 - 00046905
Fecha vto: 30/09/2026
"""


def test_extrae_remito_y_separa_pedido():
    remito, pedido, _, _ = extraer(PAGINA)
    assert remito == "00007-00043300"
    assert pedido == "00007-00046905"


def test_fecha_ignora_inicio_de_actividades_y_vencimiento_cai():
    assert extraer(PAGINA)[2] == "25/11/2025"
    texto = "Inicio de Actividades: 01/10/1990\nFecha vto: 30/09/2026\nentrega 03/02/2026"
    assert extraer(texto)[2] == "03/02/2026"


def test_cliente_tolera_errores_de_ocr_en_la_etiqueta():
    assert extraer(PAGINA)[3] == "SUPERMERCADOS DEL SUR SA"
    assert extraer("Sríres: DISTRIBUIDORA NORTE SRL  Clente: 12")[3] == "DISTRIBUIDORA NORTE SRL"


def test_fecha_de_encabezado_descarta_anios_imposibles():
    assert fecha_de_encabezado("00007-00041286\n22/07/2098\n01/10/1990") == ""
    assert fecha_de_encabezado("00007-00041286\n22/07/2025") == "22/07/2025"


def test_decidir_la_zona_del_numero_pesa_mas_que_la_pagina():
    # La página leyó un 5 como 9; la zona (solo dígitos) lo leyó bien dos veces.
    texto = "REMITO 00007 - 00046395\nPedido N°: X - 00007 - 00050154"
    zona = [("00007", "00046355"), ("00007", "00046355")]
    remito, dudoso, alternativas = decidir(texto, zona, "00007-00046355")
    assert remito == "00007-00046355"
    assert dudoso and alternativas == "00007-00046395"


def test_decidir_no_confunde_con_el_pedido():
    texto = "Pedido N°: PEDV - 00007 - 00046905\nREMITO 00007 - 00043300"
    remito, dudoso, _ = decidir(texto, [], "")
    assert remito == "00007-00043300" and not dudoso


def test_decidir_lectura_coherente_no_es_dudosa():
    zona = [("00007", "00043300"), ("00007", "00043300")]
    assert decidir("REMITO 00007 - 00043300", zona, "x") == ("00007-00043300", False, "")


def test_decidir_digito_de_menos_queda_dudoso_sin_inventar_numero():
    zona = [("00007", "0004604"), ("00007", "0004604")]
    remito, dudoso, alternativas = decidir("REMITO 00007 - 0004604", zona, "x")
    assert remito == "" and dudoso and alternativas == "00007-0004604"


def test_decidir_digito_extra_al_final_se_trunca():
    # Una raya pegada al número suele leerse como un dígito más al final.
    zona = [("00007", "000489987")]
    remito, dudoso, _ = decidir("", zona, "00007-000489987")
    assert remito == "00007-00048998" and dudoso
