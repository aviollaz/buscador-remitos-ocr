"""Índice SQLite incremental: solo se leen archivos nuevos, modificados o leídos con una
versión anterior del programa. Se puede cortar en cualquier momento y retomar.

Se guarda el texto leído de cada archivo (y el de la zona del número), y los datos se
calculan a partir de él (extraccion.extraer). Si cambia config.toml, los datos se
recalculan sin volver a hacer OCR."""

import os
import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import PurePath

from . import config
from .campos import CAMPOS, normalizar, plano
from .extraccion import extraer

# Versión de la lógica de lectura (OCR). Al subirla, "indexar" relee lo que haga falta:
#   < 3: todo (cambió la lectura del número)
#   < 4: solo los documentos donde no se había detectado número
VERSION = 4
DATOS = [c.nombre for c in CAMPOS] + ["dudoso", "alternativas"]
ESQUEMA = [("ruta", "TEXT PRIMARY KEY"), ("mtime", "REAL"), ("version", "INTEGER"),
           ("parcial", "INTEGER DEFAULT 0"), ("texto", "TEXT"), ("texto_zona", "TEXT"),
           ("dudoso", "INTEGER DEFAULT 0"), ("alternativas", "TEXT")]
ESQUEMA += [(c.nombre, "REAL" if c.tipo == "monto" else "TEXT") for c in CAMPOS]
COMMIT_CADA = 20
LOTE = 500


def _renombrar_indice_viejo():
    """El índice del programa se llamaba remitos.db: se renombra una sola vez (solo el del
    programa, nunca uno indicado con otra ruta)."""
    if (config.DB == config.DB_POR_DEFECTO and not os.path.exists(config.DB)
            and os.path.exists(config.DB_VIEJA)):
        for sufijo in ("", "-wal", "-shm"):
            if os.path.exists(config.DB_VIEJA + sufijo):
                os.replace(config.DB_VIEJA + sufijo, config.DB + sufijo)


def conectar(db=None):
    if db is None:
        _renombrar_indice_viejo()
    con = sqlite3.connect(db or config.DB)
    con.create_function("plano", 1, plano, deterministic=True)
    con.execute("PRAGMA journal_mode=WAL")      # permite buscar mientras se indexa
    cols = [r[1] for r in con.execute("PRAGMA table_info(docs)")]
    if cols:
        _migrar(con, cols)
    else:
        con.execute(f"CREATE TABLE docs ({', '.join(f'{n} {t}' for n, t in ESQUEMA)})")
    con.execute("CREATE TABLE IF NOT EXISTS meta (clave TEXT PRIMARY KEY, valor TEXT)")
    # Sin este índice, "numero IS NULL" lee el texto completo de cada fila
    con.execute("CREATE INDEX IF NOT EXISTS docs_numero ON docs(numero)")
    con.commit()
    return con


def _migrar(con, cols):
    """Índices de versiones anteriores: se adaptan sin perder datos ni volver a leer."""
    viejo = "remito" in cols
    if viejo:
        con.execute("ALTER TABLE docs RENAME COLUMN remito TO numero")
        cols = ["numero" if c == "remito" else c for c in cols]
    for nombre, tipo in ESQUEMA:
        if nombre not in cols:
            con.execute(f"ALTER TABLE docs ADD COLUMN {nombre} {tipo}")
    if viejo:          # vacíos como NULL y fechas dd/mm/aaaa → aaaa-mm-dd
        for c in CAMPOS:
            con.execute(f"UPDATE docs SET {c.nombre} = NULL WHERE {c.nombre} = ''")
        fechas = con.execute("SELECT ruta, fecha FROM docs WHERE fecha LIKE '%/%'").fetchall()
        con.executemany("UPDATE docs SET fecha = ? WHERE ruta = ?",
                        [(normalizar("fecha", f), r) for r, f in fechas])


def calcular(texto, texto_zona, previo=None):
    """Datos de un documento a partir de lo leído. Los leídos por versiones que no guardaban
    la zona del número (texto_zona NULL) conservan el número y la fecha que ya tenían."""
    datos = extraer(texto or "", texto_zona or "")
    if texto_zona is None and previo:
        for k in ("numero", "dudoso", "alternativas"):
            datos[k] = previo[k]
        datos["fecha"] = previo["fecha"] or datos["fecha"]
    return datos


def _actualizar(con, ruta, valores):
    con.execute(f"UPDATE docs SET {', '.join(f'{k} = ?' for k in valores)} WHERE ruta = ?",
                [*valores.values(), ruta])


def reextraer(con):
    """Si cambió la forma de extraer los datos (config.toml), los recalcula para todo el
    índice a partir del texto guardado. Devuelve cuántos documentos actualizó."""
    guardada = con.execute("SELECT valor FROM meta WHERE clave = 'huella'").fetchone()
    if guardada and guardada[0] == config.CFG.huella:
        return 0
    rutas = [r for (r,) in con.execute("SELECT ruta FROM docs")]
    for i in range(0, len(rutas), LOTE):
        lote = rutas[i:i + LOTE]
        for ruta, texto, zona, *previo in con.execute(
                "SELECT ruta, texto, texto_zona, numero, dudoso, alternativas, fecha FROM docs "
                f"WHERE ruta IN ({', '.join('?' * len(lote))})", lote).fetchall():
            previo = dict(zip(("numero", "dudoso", "alternativas", "fecha"), previo))
            _actualizar(con, ruta, calcular(texto, zona, previo))
        con.commit()                       # de a lotes: no bloquea a quien busca mientras
    con.execute("INSERT OR REPLACE INTO meta VALUES ('huella', ?)", (config.CFG.huella,))
    con.commit()
    return len(rutas)


def hay_que_leer(ruta, previo):
    if previo is None:
        return True
    mtime, version, numero = previo
    version = version or 1
    if mtime != os.path.getmtime(ruta) or version < 3:
        return True
    return version < VERSION and not numero


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
    """Lee los archivos en paralelo y va devolviendo (ruta, texto, texto_zona, error)."""
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

    # Archivos que ya no existen (movidos, carpeta renombrada, borrados): se quitan, salvo
    # que no esté disponible su disco o unidad de red (p. ej. desconectado por un rato).
    viejos = [(r,) for (r,) in con.execute("SELECT ruta FROM docs")
              if not os.path.exists(r) and os.path.exists(PurePath(r).anchor)]
    if viejos:
        con.executemany("DELETE FROM docs WHERE ruta = ?", viejos)
        con.commit()
        print(f"Se quitaron del índice {len(viejos)} archivos que ya no existen "
              f"(movidos o borrados).")
    if n := reextraer(con):
        print(f"Se actualizaron los datos de {n} documentos con la configuración actual "
              f"(sin volver a leerlos).")

    ya = {r[0]: r[1:] for r in con.execute("SELECT ruta, mtime, version, numero FROM docs")}
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
    columnas = [n for n, _ in ESQUEMA]
    for i, (ruta, texto, zona, err) in enumerate(
            _correr(pendientes, 1, workers, avance, parar), 1):
        if err:
            errores += 1
            print(f"\n  ERROR {ruta}: {err}", file=sys.stderr)
            continue
        fila = {"ruta": ruta, "mtime": os.path.getmtime(ruta), "version": VERSION,
                "parcial": 1, "texto": texto, "texto_zona": zona, **calcular(texto, zona)}
        sin_numero += not fila["numero"]
        dudosos += fila["dudoso"]
        con.execute(f"INSERT OR REPLACE INTO docs ({', '.join(columnas)}) "
                    f"VALUES ({', '.join('?' * len(columnas))})", [fila[c] for c in columnas])
        if i % COMMIT_CADA == 0:
            con.commit()
    con.commit()
    if total:
        print(f"\nLectura rápida lista. Errores: {errores}. Sin número: {sin_numero}. "
              f"Lectura dudosa: {dudosos} (marcados en el Excel del índice).")
    if parar and parar():
        return

    previos = {r: (zona, dict(zip(("numero", "dudoso", "alternativas", "fecha"), p)))
               for r, zona, *p in con.execute(
                   "SELECT ruta, texto_zona, numero, dudoso, alternativas, fecha FROM docs "
                   "WHERE parcial = 1") if os.path.exists(r)}
    for i, (ruta, texto, _, err) in enumerate(
            _correr(list(previos), 2, workers, avance, parar), 1):
        if not err:
            zona, previo = previos[ruta]
            _actualizar(con, ruta, {"texto": texto, "parcial": 0,
                                    **calcular(texto, zona, previo)})
        if i % COMMIT_CADA == 0:
            con.commit()
    con.commit()
    if previos:
        print("\nTexto completo listo.")
