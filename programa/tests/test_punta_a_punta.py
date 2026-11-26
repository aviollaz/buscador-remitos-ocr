"""Prueba completa con OCR real sobre remitos sintéticos (requiere Tesseract instalado)."""

import json
import shutil

import pytest

pytesseract = pytest.importorskip("pytesseract")
if not shutil.which("tesseract"):
    pytest.skip("Tesseract no está instalado", allow_module_level=True)


def test_indexar_y_buscar(tmp_path, monkeypatch, capsys):
    from buscador import config
    from tests.muestras import generar

    carpeta = tmp_path / "scans" / "sub"                 # también recorre subcarpetas
    verdad = generar(str(carpeta), cantidad=3, semilla=11, ocluidos=0)
    (carpeta / "verdad.json").unlink()
    (carpeta / "notas.txt").write_text("no es una imagen")
    monkeypatch.setattr(config, "DB", str(tmp_path / "t.db"))

    from buscador.busqueda import buscar_numero
    from buscador.indice import conectar, indexar

    indexar(str(tmp_path / "scans"), workers=2)
    salida = capsys.readouterr().out
    assert "3 archivos encontrados" in salida and ".txt: 1" in salida

    filas = {r: (rem, texto, parcial) for r, rem, texto, parcial in conectar().execute(
        "SELECT ruta, remito, texto, parcial FROM docs")}
    for nombre, v in verdad.items():
        remito, texto, parcial = filas[str(carpeta / nombre)]
        assert remito == v["remito"]
        assert parcial == 0 and "traslado" in texto        # el paso 2 leyó la página entera

    # Indexar de nuevo no relee nada
    indexar(str(tmp_path / "scans"), workers=2)
    assert "0 para leer" in capsys.readouterr().out

    nombre, v = next(iter(verdad.items()))
    buscar_numero(v["remito"].split("-")[1].lstrip("0"))
    out = capsys.readouterr().out
    assert nombre in out
    assert out.count("NO ENCONTRADO") == 1                # el pedido no coincide
    json.dumps(verdad)                                    # (verdad serializable)
