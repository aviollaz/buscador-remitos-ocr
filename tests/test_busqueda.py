import pytest

from remitos import indice
from remitos.busqueda import (cargar, casi, coincide, distancia, leer_lista,
                              parsear_consulta, resolver)


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
    assert not coincide("00007-00043300", (1, 43300))
    assert not coincide("", (None, 43300))


def test_distancia():
    assert distancia("00046390", "00046397") == 1    # un dígito cambiado
    assert distancia("0004639", "00046390") == 1     # un dígito de menos
    assert distancia("000489987", "00048998") == 1   # un dígito de más
    assert distancia("00046355", "00046390") == 2


def test_casi_ignora_alternativas_completas_para_no_meter_ruido():
    dudosos = [
        ("a.jpg", "00007-00046397", "", "", "", "00007-0004639"),   # dígito tapado
        ("b.jpg", "00007-00046355", "", "", "", "00007-00046395"),  # alternativa = error OCR
    ]
    rutas = [r[0] for r in casi(dudosos, (None, 46390))]
    assert rutas == ["a.jpg"]


@pytest.fixture
def con():
    c = indice.conectar(":memory:")
    filas = [
        ("r1.jpg", "00007-00043300", "00007-00046905", 0, ""),
        ("r2.jpg", "00007-00046397", "00007-00050170", 1, "00007-0004639"),
        ("r3.jpg", "", "", 1, "00007-0006"),
    ]
    for ruta, remito, pedido, dudoso, alt in filas:
        c.execute("INSERT INTO docs VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (ruta, 0, f"texto {remito} 44474", remito, pedido, "", "", 4, dudoso, alt))
    return c


def test_resolver_separa_remito_pedido_y_posibles(con):
    todas, dudosos = cargar(con)
    por_remito, posibles, por_pedido = resolver(con, todas, dudosos, (None, 43300), "43300")
    assert [r[0] for r in por_remito] == ["r1.jpg"] and not posibles and not por_pedido

    por_remito, _, por_pedido = resolver(con, todas, dudosos, (None, 46905), "46905")
    assert not por_remito and [r[0] for r in por_pedido] == ["r1.jpg"]

    por_remito, posibles, _ = resolver(con, todas, dudosos, (None, 46390), "46390")
    assert not por_remito and [r[0] for r in posibles] == ["r2.jpg"]


def test_resolver_busca_en_texto_solo_documentos_sin_numero(con):
    todas, dudosos = cargar(con)
    _, posibles, _ = resolver(con, todas, dudosos, (None, 44474), "44474")
    assert [r[0] for r in posibles] == ["r3.jpg"]


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
