import os
import sqlite3

from remitos import indice


def test_migra_indice_de_version_anterior_sin_perder_datos(tmp_path):
    db = tmp_path / "viejo.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE docs (ruta TEXT PRIMARY KEY, mtime REAL, texto TEXT, remito TEXT, "
              "pedido TEXT, fecha TEXT, cliente TEXT)")
    c.execute("INSERT INTO docs VALUES ('a.jpg', 1, 't', '00007-00043300', '', '', '')")
    c.commit()
    c.close()

    con = indice.conectar(str(db))
    cols = [r[1] for r in con.execute("PRAGMA table_info(docs)")]
    assert cols == indice.COLUMNAS
    assert con.execute("SELECT remito, version, dudoso FROM docs").fetchone() == \
        ("00007-00043300", 1, 0)


def test_hay_que_leer(tmp_path):
    f = tmp_path / "x.jpg"
    f.write_bytes(b"")
    m = os.path.getmtime(f)
    v = indice.VERSION
    assert indice.hay_que_leer(str(f), None)                       # nuevo
    assert indice.hay_que_leer(str(f), (m - 10, v, "00007-1"))     # modificado
    assert indice.hay_que_leer(str(f), (m, 2, "00007-1"))          # lógica vieja: releer todo
    assert indice.hay_que_leer(str(f), (m, 3, ""))                 # v3 sin número: releer
    assert not indice.hay_que_leer(str(f), (m, 3, "00007-1"))      # v3 con número: no
    assert not indice.hay_que_leer(str(f), (m, v, ""))             # al día
