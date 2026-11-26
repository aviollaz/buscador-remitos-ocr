import os
import sqlite3
from unittest import mock

import pytest

from buscador import config, indice

REMITO = "REMITO\n00007 - 00043300\nSr/res: HELADOS LA ESQUINA SRL  Cliente: 029257\n"


@pytest.fixture
def db(tmp_path, monkeypatch):
    ruta = str(tmp_path / "t.db")
    monkeypatch.setattr(config, "DB", ruta)
    return ruta


def test_migra_indice_de_la_primera_version(db):
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE docs (ruta TEXT PRIMARY KEY, mtime REAL, texto TEXT, remito TEXT, "
              "pedido TEXT, fecha TEXT, cliente TEXT)")
    c.execute("INSERT INTO docs VALUES ('a.jpg', 1, 't', '00007-00043300', '', '25/11/2025', '')")
    c.commit()
    c.close()

    con = indice.conectar()
    cols = [r[1] for r in con.execute("PRAGMA table_info(docs)")]
    assert set(cols) == {n for n, _ in indice.ESQUEMA}
    assert con.execute("SELECT numero, pedido, fecha, texto_zona FROM docs").fetchone() == \
        ("00007-00043300", None, "2025-11-25", None)


def test_migra_indice_v4_y_recalcula_sin_ocr_conservando_el_numero(db):
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE docs (ruta TEXT PRIMARY KEY, mtime REAL, texto TEXT, remito TEXT, "
              "pedido TEXT, fecha TEXT, cliente TEXT, version INTEGER, dudoso INTEGER, "
              "alternativas TEXT, parcial INTEGER)")
    # El número salió de la zona (votación) y no se puede recalcular: se conserva
    c.execute("INSERT INTO docs VALUES ('a.jpg', 1, ?, '00007-00043399', '', '04/01/2026', "
              "'', 4, 1, '00007-00043300', 0)", (REMITO,))
    c.commit()
    c.close()

    con = indice.conectar()
    with mock.patch("buscador.ocr.procesar", side_effect=AssertionError("no hay que leer")):
        assert indice.reextraer(con) == 1
    fila = con.execute("SELECT tipo, numero, dudoso, alternativas, fecha, cliente, cod_cliente "
                       "FROM docs").fetchone()
    assert fila == ("remito", "00007-00043399", 1, "00007-00043300", "2026-01-04",
                    "HELADOS LA ESQUINA SRL", "29257")
    assert indice.reextraer(con) == 0                     # ya está al día


def test_reextrae_todo_cuando_cambia_la_configuracion(db, monkeypatch):
    con = indice.conectar()
    con.execute("INSERT INTO docs (ruta, texto, texto_zona) VALUES ('a.jpg', ?, '')", (REMITO,))
    assert indice.reextraer(con) == 1
    assert con.execute("SELECT cliente FROM docs").fetchone() == ("HELADOS LA ESQUINA SRL",)

    datos = {"general": {"tipo_por_defecto": "remito"}, "ocr": config.CFG.ocr,
             "tipos": {"remito": {"nombre": "Remito", "titulo": "REMITO",
                                  "numero": [r"(\d{4,5}) - (\d{8})"],
                                  "campos": {"cod_cliente": r"Cliente: (\d+)"}}}}
    monkeypatch.setattr(config, "CFG", config.compilar(datos))
    assert indice.reextraer(con) == 1
    assert con.execute("SELECT numero, cliente, cod_cliente FROM docs").fetchone() == \
        ("00007-00043300", None, "29257")


def test_hay_que_leer(tmp_path):
    f = tmp_path / "x.jpg"
    f.write_bytes(b"")
    m = os.path.getmtime(f)
    v = indice.VERSION
    assert indice.hay_que_leer(str(f), None)                       # nuevo
    assert indice.hay_que_leer(str(f), (m - 10, v, "00007-1"))     # modificado
    assert indice.hay_que_leer(str(f), (m, 2, "00007-1"))          # lógica vieja: releer todo
    assert indice.hay_que_leer(str(f), (m, 3, None))               # v3 sin número: releer
    assert not indice.hay_que_leer(str(f), (m, 3, "00007-1"))      # v3 con número: no
    assert not indice.hay_que_leer(str(f), (m, v, None))           # al día


def test_indexar_quita_archivos_que_ya_no_existen(tmp_path, db):
    con = indice.conectar()
    movido = str(tmp_path / "vieja" / "r.jpg")          # su disco existe: se quita
    desconectado = "Q:/remitos/r.jpg"                    # su unidad no está: se conserva
    for r in (movido, desconectado):
        con.execute("INSERT INTO docs (ruta, numero) VALUES (?, '00007-00000001')", (r,))
    con.commit()
    (tmp_path / "scans").mkdir()

    indice.indexar(str(tmp_path / "scans"), workers=1)
    assert [r for (r,) in indice.conectar().execute("SELECT ruta FROM docs")] == [desconectado]


def test_renombra_el_indice_viejo_solo_si_es_el_del_programa(tmp_path, monkeypatch):
    viejo, nuevo = tmp_path / "remitos.db", tmp_path / "indice.db"
    sqlite3.connect(viejo).close()
    monkeypatch.setattr(config, "DB_VIEJA", str(viejo))
    monkeypatch.setattr(config, "DB_POR_DEFECTO", str(nuevo))

    monkeypatch.setattr(config, "DB", str(tmp_path / "otro.db"))   # otra ruta: no se toca
    indice.conectar().close()
    assert viejo.exists()

    monkeypatch.setattr(config, "DB", str(nuevo))
    indice.conectar().close()
    assert not viejo.exists() and nuevo.exists()
