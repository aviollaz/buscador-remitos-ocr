import pytest

from buscador import indice
from buscador.busqueda import (Filtro, buscar, casi, coincide, distancia, leer_lista,
                               parsear_consulta)


@pytest.mark.parametrize("entrada, esperado", [
    ("43300", (None, 43300)),
    ("00007-00043300", (7, 43300)),
    ("00007 - 00043300", (7, 43300)),
    ("R 00007-00043300", (7, 43300)),
    ("43300.0", (None, 43300)),            # así llegan los números desde Excel
    (43300, (None, 43300)),
    ("sin numero", None),
])
def test_parsear_consulta(entrada, esperado):
    assert parsear_consulta(entrada) == esperado


def test_coincide_con_y_sin_punto_de_venta():
    assert coincide("00007-00043300", (None, 43300))
    assert coincide("00007-00043300", (7, 43300))
    assert coincide("00007-00012345;00007-00043300", (None, 43300))
    assert not coincide("00007-00043300", (1, 43300))
    assert not coincide(None, (None, 43300))


def test_distancia():
    assert distancia("00046390", "00046397") == 1    # un dígito cambiado
    assert distancia("0004639", "00046390") == 1     # un dígito de menos
    assert distancia("000489987", "00048998") == 1   # un dígito de más
    assert distancia("00046355", "00046390") == 2


def test_casi_ignora_alternativas_completas_para_no_meter_ruido():
    dudosos = [
        {"ruta": "a.jpg", "numero": "00007-00046397", "alternativas": "00007-0004639"},
        {"ruta": "b.jpg", "numero": "00007-00046355", "alternativas": "00007-00046395"},
    ]
    assert [f["ruta"] for f in casi(dudosos, (None, 46390))] == ["a.jpg"]


def agregar(con, ruta, texto="", **datos):
    fila = {"ruta": ruta, "mtime": 0, "version": indice.VERSION, "parcial": 0,
            "texto": texto, "texto_zona": "", "dudoso": 0, **datos}
    con.execute(f"INSERT INTO docs ({', '.join(fila)}) VALUES ({', '.join('?' * len(fila))})",
                list(fila.values()))


@pytest.fixture
def con():
    c = indice.conectar(":memory:")
    agregar(c, "r1.jpg", "texto 44474", tipo="remito", numero="00007-00043300",
            pedido="00007-00046905", fecha="2026-01-10", cliente="SUPERMERCADOS DEL SUR SA",
            cod_cliente="1234", cuit="30-71162133-0")
    agregar(c, "r2.jpg", tipo="remito", numero="00007-00046397", pedido="00007-00050170",
            fecha="2026-02-20", cliente="HELADOS LA ESQUINA SRL", cod_cliente="29257",
            dudoso=1, alternativas="00007-0004639")
    agregar(c, "r3.jpg", "ilegible 44474", tipo="remito", dudoso=1, alternativas="00007-0006")
    agregar(c, "f1.pdf", tipo="factura", numero="00002-00000123", fecha="2026-01-15",
            cliente="SUPERMERCADOS DEL SUR SA", cuit="30-71162133-0", monto=1500.0,
            citados="00007-00043300", pedido="00007-00046905")
    agregar(c, "f2.pdf", tipo="factura", numero="00002-00000124", fecha="2026-03-01",
            cliente="Confitería Belgrano SA", monto=99.5, pedido="00007-00050170")
    return c


def rutas(con, **filtro):
    return [(r.fila or {}).get("ruta") for r in buscar(con, Filtro(**filtro))]


def etiquetas(con, vinculados=False, **filtro):
    return [(r.etiqueta, (r.fila or {}).get("ruta"))
            for r in buscar(con, Filtro(**filtro), vinculados)]


def test_numeros_exacto_posible_por_pedido_y_no_encontrado(con):
    assert etiquetas(con, numeros=["43300"]) == [("Encontrado", "r1.jpg")]
    assert etiquetas(con, numeros=["46390"]) == [("Posible (revisar)", "r2.jpg")]
    assert etiquetas(con, numeros=["44474"]) == [("Posible (revisar)", "r3.jpg")]  # en texto
    assert etiquetas(con, numeros=["46905"]) == [("Solo por pedido (revisar)", "r1.jpg"),
                                                 ("Solo por pedido (revisar)", "f1.pdf")]
    assert etiquetas(con, numeros=["99999999"]) == [("NO ENCONTRADO", None)]


def test_filtro_por_fechas_monto_y_tipo(con):
    assert rutas(con, desde="2026-01-12", hasta="2026-02-28") == ["f1.pdf", "r2.jpg"]
    assert rutas(con, monto_op=">", monto=1000) == ["f1.pdf"]
    assert rutas(con, monto_op="<", monto=100) == ["f2.pdf"]
    assert rutas(con, monto_op="=", monto=1500) == ["f1.pdf"]
    assert rutas(con, tipo="factura") == ["f1.pdf", "f2.pdf"]


def test_filtro_por_monto_no_esconde_facturas_sin_monto(con):
    agregar(con, "f3.pdf", tipo="factura", numero="00002-00000125", fecha="2026-04-01")
    assert etiquetas(con, monto_op=">", monto=1000) == [
        ("", "f1.pdf"), ("Sin monto (revisar)", "f3.pdf")]   # los remitos no tienen monto
    assert etiquetas(con, numeros=["125"], monto_op="<", monto=100) == [
        ("Encontrado - sin monto (revisar)", "f3.pdf")]


def test_filtro_por_clientes_nombre_codigo_cuit_y_lista(con):
    assert rutas(con, clientes=["supermercados"]) == ["r1.jpg", "f1.pdf"]
    assert rutas(con, clientes=["029257"]) == ["r2.jpg"]
    assert rutas(con, clientes=["30-71162133-0"]) == ["r1.jpg", "f1.pdf"]
    assert rutas(con, clientes=["confiteria"]) == ["f2.pdf"]          # sin acento
    assert rutas(con, clientes=["helados", "belgrano"]) == ["r2.jpg", "f2.pdf"]


def test_filtro_por_texto_y_combinado_con_numeros(con):
    assert sorted(rutas(con, texto="44474")) == ["r1.jpg", "r3.jpg"]
    assert etiquetas(con, numeros=["43300", "123"], tipo="factura") == [
        ("NO ENCONTRADO", None), ("Encontrado", "f1.pdf")]


def test_vinculados_en_los_dos_sentidos_sin_repetir(con):
    # f1 cita a r1 y además comparte su pedido: r1 aparece una sola vez
    assert etiquetas(con, True, numeros=["123"]) == [
        ("Encontrado", "f1.pdf"), ("Remito de factura 00002-00000123", "r1.jpg")]
    assert etiquetas(con, True, numeros=["43300"]) == [
        ("Encontrado", "r1.jpg"), ("Factura de remito 00007-00043300", "f1.pdf")]
    # por pedido en común (la factura no cita remitos)
    assert etiquetas(con, True, numeros=["124"]) == [
        ("Encontrado", "f2.pdf"), ("Remito de factura 00002-00000124", "r2.jpg")]


def test_leer_lista_txt_y_excel(tmp_path):
    txt = tmp_path / "lista.txt"
    txt.write_text("Remitos\n43300\n00007 - 00043504\n\n", encoding="utf-8")
    assert leer_lista(str(txt)) == ["43300", "00007 - 00043504"]

    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    for fila in (["Remito", "Importe"], [43300, 1234.5], ["00007-00043504", 10]):
        wb.active.append(fila)
    xlsx = tmp_path / "lista.xlsx"
    wb.save(xlsx)
    assert leer_lista(str(xlsx)) == ["43300", "00007-00043504"]

    with pytest.raises(ValueError, match="xls"):
        leer_lista(str(tmp_path / "viejo.xls"))
