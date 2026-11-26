"""Índice SQLite incremental: solo se leen archivos nuevos, modificados o leídos con una
versión anterior del programa. Se puede cortar en cualquier momento y retomar."""

import os
import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

from . import config

# Versión de la lógica de lectura. Al subirla, "indexar" relee lo que haga falta:
#   < 3: todo (cambió la lectura del número)
#   < 4: solo los documentos donde no se había detectado número
VERSION = 4
COLUMNAS = ["ruta", "mtime", "texto", "remito", "pedido", "fecha", "cliente", "version",
            "dudoso", "alternativas", "parcial"]
_TIPOS_NUEVOS = {"version": "INTEGER DEFAULT 1", "dudoso": "INTEGER DEFAULT 0",
                 "alternativas": "TEXT DEFAULT ''", "parcial": "INTEGER DEFAULT 0"}
COMMIT_CADA = 20


def conectar(db=None):
    con = sqlite3.connect(db or config.DB)
    con.execute("PRAGMA journal_mode=WAL")      # permite buscar mientras se indexa
    cols = [r[1] for r in con.execute("PRAGMA table_info(docs)")]
    if cols and cols == COLUMNAS[:len(cols)]:
        for c in COLUMNAS[len(cols):]:          # índice de una versión anterior: se migra
            con.execute(f"ALTER TABLE docs ADD COLUMN {c} {_TIPOS_NUEVOS[c]}")
    elif cols:                                   # esquema desconocido: se rehace
        con.execute("DROP TABLE docs")
    con.execute("""CREATE TABLE IF NOT EXISTS docs (
        ruta TEXT PRIMARY KEY, mtime REAL, texto TEXT,
        remito TEXT, pedido TEXT, fecha TEXT, cliente TEXT, version INTEGER,
        dudoso INTEGER DEFAULT 0, alternativas TEXT DEFAULT '', parcial INTEGER DEFAULT 0)""")
    return con


def hay_que_leer(ruta, previo):
    if previo is None:
        return True
    mtime, version, remito = previo
    version = version or 1
    if mtime != os.path.getmtime(ruta) or version < 3:
        return True
    return version < VERSION and not remito


def buscar_archivos(carpeta, ya):
    """Recorre la carpeta (y subcarpetas). Devuelve (pendientes, cantidad_vista, ignorados)."""
    pendientes, ignorados, vistos = [], {}, 0
    for raiz, _, archivos in os.walk(carpeta):
        for a in archivos:
            ext = os.path.splitext(a)[1].lower() or "(sin extensión)"
            if ext not in config.EXTS:
                ignorados[ext] = ignorados.get(ext, 0) + 1
                continue
            vistos += 1
            p = os.path.abspath(os.path.join(raiz, a))
            if hay_que_leer(p, ya.get(p)):
                pendientes.append(p)
    return pendientes, vistos, ignorados


def _avance_consola(paso, i, total):
    print(f"\r  Paso {paso}/2: {i}/{total}", end="", flush=True)


def _correr(rutas, paso, workers, avance, parar):
    """Procesa los archivos en paralelo y va devolviendo las filas a medida que terminan."""
    from .ocr import procesar

    with ProcessPoolExecutor(max_workers=workers) as ex:
        futuros = [ex.submit(procesar, p, paso) for p in rutas]
        for i, f in enumerate(as_completed(futuros), 1):
            yield f.result()
            avance(paso, i, len(rutas))
            if parar and parar():
                ex.shutdown(cancel_futures=True)
                return


def indexar(carpeta, workers=None, avance=_avance_consola, parar=None):
    """Paso 1: lectura rápida (solo el encabezado): deja todo buscable por número cuanto antes.
    Paso 2: texto completo de la página, para la búsqueda por texto.
    `parar` es una función que devuelve True para cortar (se retoma en la próxima vez)."""
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    con = conectar()
    carpeta = carpeta.strip().strip('"').strip()
    print(f"Carpeta: {carpeta}  (incluye subcarpetas)")
    if not os.path.isdir(carpeta):
        sys.exit("ERROR: esa carpeta no existe o no se puede abrir. Revisá la ruta.")

    ya = {r[0]: r[1:] for r in con.execute("SELECT ruta, mtime, version, remito FROM docs")}
    pendientes, vistos, ignorados = buscar_archivos(carpeta, ya)
    total = len(pendientes)
    print(f"{vistos} archivos encontrados (imágenes/PDF), {total} para leer "
          f"(nuevos, modificados o a releer con la versión nueva).")
    if ignorados:
        print("Archivos ignorados: " + ", ".join(
            f"{e}: {n}" for e, n in sorted(ignorados.items(), key=lambda x: -x[1])))
    if vistos == 0 and not ignorados:
        print("La carpeta está vacía. Si los archivos están en OneDrive o en un .zip, "
              "descargalos/descomprimilos primero.")
    if any(p.lower().endswith(".pdf") for p in pendientes):
        try:
            import pymupdf  # noqa: F401
        except ImportError:
            sys.exit("ERROR: falta la librería para PDF. Ejecutá: pip install pymupdf")

    errores = sin_numero = dudosos = 0
    for i, fila in enumerate(_correr(pendientes, 1, workers, avance, parar), 1):
        ruta, texto, remito, pedido, fecha, cliente, dudoso, alternativas, err = fila
        if err:
            errores += 1
            print(f"\n  ERROR {ruta}: {err}", file=sys.stderr)
            continue
        sin_numero += not remito
        dudosos += dudoso
        con.execute("INSERT OR REPLACE INTO docs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (ruta, os.path.getmtime(ruta), texto, remito, pedido, fecha, cliente,
                     VERSION, dudoso, alternativas, 1))
        if i % COMMIT_CADA == 0:
            con.commit()
    con.commit()
    if total:
        print(f"\nLectura rápida lista. Errores: {errores}. Sin número de remito: {sin_numero}. "
              f"Lectura dudosa: {dudosos} (marcados en el Excel del índice).")
    if parar and parar():
        return

    parciales = [r for (r,) in con.execute("SELECT ruta FROM docs WHERE parcial = 1")
                 if os.path.exists(r)]
    for i, fila in enumerate(_correr(parciales, 2, workers, avance, parar), 1):
        ruta, texto, _, pedido, fecha, cliente, *_, err = fila
        if not err:   # con el texto completo se completan los datos que faltaran
            con.execute("""UPDATE docs SET texto = ?, parcial = 0,
                pedido = CASE WHEN pedido = '' THEN ? ELSE pedido END,
                fecha = CASE WHEN fecha = '' THEN ? ELSE fecha END,
                cliente = CASE WHEN cliente = '' THEN ? ELSE cliente END
                WHERE ruta = ?""", (texto, pedido, fecha, cliente, ruta))
        if i % COMMIT_CADA == 0:
            con.commit()
    con.commit()
    if parciales:
        print("\nTexto completo listo.")
