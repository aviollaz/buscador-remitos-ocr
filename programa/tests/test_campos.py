import pytest

from buscador.campos import mostrar, normalizar, plano


@pytest.mark.parametrize("crudo, esperado", [
    ("1.234,56", 1234.56), ("1234,56", 1234.56), ("1,234.56", 1234.56), ("1234.56", 1234.56),
    ("$ 1.234.567,89", 1234567.89), ("1.234", 1234.0), ("500", 500.0), ("sin monto", None),
])
def test_monto(crudo, esperado):
    assert normalizar("monto", crudo) == esperado


@pytest.mark.parametrize("crudo, esperado", [
    ("25/11/2025", "2025-11-25"), ("5 / 3 / 2026", "2026-03-05"), ("25/11/25", "2025-11-25"),
    ("31/02/2026", None), ("01/10/1990", None), ("nada", None),
])
def test_fecha(crudo, esperado):
    assert normalizar("fecha", crudo) == esperado


def test_cuit_codigo_y_comprobantes():
    assert normalizar("cuit", "30 - 58962149 - 9") == "30-58962149-9"
    assert normalizar("cuit", "30-589621-9") is None
    assert normalizar("codigo", "021300") == "21300"
    assert normalizar("comprobante", "0025-00063300, 25 - 63301 y 0025-00063300") == \
        "00025-00063300;00025-00063301"


def test_mostrar_y_plano():
    assert mostrar("fecha", "2025-11-25") == "25/11/2025"
    assert mostrar("monto", 1234567.891) == "1.234.567,89"
    assert mostrar("texto", None) == ""
    assert plano("Confitería BELGRANO") == "confiteria belgrano"
