"""Prueba completa con OCR real sobre remitos sintéticos y una factura PDF sintética
(requiere Tesseract instalado)."""

import shutil

import pytest

pytesseract = pytest.importorskip("pytesseract")
pytest.importorskip("pymupdf")
if not shutil.which("tesseract"):
    pytest.skip("Tesseract no está instalado", allow_module_level=True)


def test_indexar_y_buscar_remitos_y_facturas(tmp_path, capsys):
    from buscador.busqueda import Filtro, buscar
    from buscador.indice import conectar, indexar
    from tests.muestras import generar, generar_factura_pdf

    carpeta = tmp_path / "scans" / "sub"                 # también recorre subcarpetas
    verdad = generar(str(carpeta), cantidad=3, semilla=11, ocluidos=0)
    (carpeta / "verdad.json").unlink()
    (carpeta / "notas.txt").write_text("no es una imagen")
    remitos = [v["remito"] for v in verdad.values()]
    generar_factura_pdf(str(tmp_path / "scans" / "factura.pdf"), "00002-00000123",
                        remitos[:2], "HELADOS LA ESQUINA SRL", "15/03/2026", "1.234.567,89")

    totales = {}
    indexar(str(tmp_path / "scans"), workers=2,
            avance=lambda paso, i, total: totales.update({paso: total}))
    salida = capsys.readouterr().out
    assert "4 archivos encontrados" in salida and ".txt: 1" in salida
    assert totales == {1: 4, 2: 3}        # la factura (PDF digital) no se relee en el paso 2

    con = conectar()
    filas = {r: (tipo, numero, texto, parcial) for r, tipo, numero, texto, parcial in
             con.execute("SELECT ruta, tipo, numero, texto, parcial FROM docs")}
    for nombre, v in verdad.items():
        tipo, numero, texto, parcial = filas[str(carpeta / nombre)]
        assert (tipo, numero) == ("remito", v["remito"])
        # El paso 2 leyó la página entera: aparece algo del pie. Con escaneos degradados cada
        # versión de Tesseract lee mal una parte distinta del pie (en Windows sale "traslado"
        # y no la fecha; en Linux al revés), así que alcanza con cualquiera.
        pie = ("traslado", "30/09/2026", "C.A.I", "entrega")
        assert parcial == 0 and any(p in texto for p in pie), texto
    factura = con.execute("SELECT tipo, numero, fecha, cliente, cod_cliente, citados, monto "
                          "FROM docs WHERE ruta LIKE '%factura.pdf'").fetchone()
    assert factura == ("factura", "00002-00000123", "2026-03-15", "HELADOS LA ESQUINA SRL",
                       "29257", ";".join(remitos[:2]), 1234567.89)

    # Indexar de nuevo no relee nada
    indexar(str(tmp_path / "scans"), workers=2)
    assert "0 para leer" in capsys.readouterr().out

    # Con el número de la factura salen sus dos remitos
    res = buscar(con, Filtro(numeros=["123"]), con_vinculados=True)
    assert [(r.etiqueta, r.fila["numero"]) for r in res] == [
        ("Encontrado", "00002-00000123")] + [
        ("Remito de factura 00002-00000123", n) for n in sorted(remitos[:2])]

    # Filtros: tipo y monto
    assert [r.fila["numero"] for r in buscar(con, Filtro(tipo="factura", monto_op=">",
                                                          monto=1000))] == ["00002-00000123"]
