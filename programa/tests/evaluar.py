"""Evalúa la precisión del buscador sobre remitos sintéticos con verdad conocida.

Compara dos estrategias para obtener el número de remito:
  solo_pagina     primer número con formato de comprobante en la página que no sea el
                  del pedido (OCR general de la página completa)
  pagina_y_zona   lo anterior + relectura de la zona del número solo con dígitos +
                  votación entre lecturas (versión actual)

y mide qué tan "encontrable" queda cada remito con la búsqueda real (exacta + posibles).

Uso:  python tests/evaluar.py --cantidad 100 --ocluidos 0.1
"""

import argparse
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buscador import busqueda  # noqa: E402
from buscador.campos import normalizar  # noqa: E402
from buscador.extraccion import extraer  # noqa: E402
from buscador.ocr import procesar  # noqa: E402
from tests.muestras import generar  # noqa: E402


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cantidad", type=int, default=100)
    ap.add_argument("--ocluidos", type=float, default=0.1)
    ap.add_argument("--semilla", type=int, default=7)
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="eval_remitos_")
    print(f"Generando {a.cantidad} remitos sintéticos en {tmp} ...")
    verdad = generar(tmp, a.cantidad, a.semilla, a.ocluidos)

    rutas = [os.path.join(tmp, n) for n in sorted(verdad)]
    t0 = time.time()
    with ProcessPoolExecutor() as ex:
        filas = list(ex.map(procesar, rutas))
    segs = time.time() - t0

    from collections import defaultdict
    por_calidad = defaultdict(lambda: {"n": 0, "solo_pagina": 0, "pagina_y_zona": 0})
    ok_fecha = ok_cliente = 0
    n_ocl = ocl_dudoso = 0
    limpios = limpios_dudosos = 0
    docs = []
    for ruta, texto, texto_zona, err in filas:
        assert not err, err
        d = extraer(texto, texto_zona)
        remito, fecha, cliente, dudoso = d["numero"], d["fecha"], d["cliente"] or "", d["dudoso"]
        v = verdad[os.path.basename(ruta)]
        solo_pagina = extraer(texto)           # sin la relectura de la zona del número
        sin_pedido = [x for x in (solo_pagina["numero"] or "").split(";") if x]
        c = por_calidad["con dígito tapado" if v["ocluido"] else v["calidad"]]
        c["n"] += 1
        c["solo_pagina"] += bool(sin_pedido) and sin_pedido[0] == v["remito"]
        c["pagina_y_zona"] += remito == v["remito"]
        ok_fecha += fecha == normalizar("fecha", v["fecha"])
        ok_cliente += cliente.strip().upper() == v["cliente"]
        if v["ocluido"]:
            n_ocl += 1
            ocl_dudoso += bool(dudoso)
        else:
            limpios += 1
            limpios_dudosos += bool(dudoso) and remito == v["remito"]
        docs.append({"ruta": ruta, "dudoso": dudoso, "alternativas": d["alternativas"],
                     "numero": remito, "pedido": d["pedido"]})

    # Búsqueda real: ¿aparece el archivo correcto al buscar su número?
    todas, dudosos = docs, [d for d in docs if d["dudoso"]]
    exacto = posible = perdido = ajenos = 0
    perdidos_ocl = 0
    for ruta in rutas:
        v = verdad[os.path.basename(ruta)]
        consulta = busqueda.parsear_consulta(v["remito"])
        por_remito = [f for f in todas if busqueda.coincide(f["numero"], consulta)]
        posibles = busqueda.casi(dudosos, consulta, {f["ruta"] for f in por_remito})
        ajenos += sum(f["ruta"] != ruta for f in por_remito)
        if any(f["ruta"] == ruta for f in por_remito):
            exacto += 1
        elif any(f["ruta"] == ruta for f in posibles):
            posible += 1
        else:
            perdido += 1
            perdidos_ocl += v["ocluido"]

    n = len(rutas)
    res = {
        "documentos": n,
        "con_digito_tapado": n_ocl,
        "precision_numero_por_calidad": {
            k: {"docs": c["n"], "solo_pagina": pct(c["solo_pagina"], c["n"]),
                "pagina_y_zona": pct(c["pagina_y_zona"], c["n"])}
            for k, c in sorted(por_calidad.items())},
        "precision_numero_total": {
            e: pct(sum(c[e] for c in por_calidad.values()), n)
            for e in ("solo_pagina", "pagina_y_zona")},
        "fecha_correcta": pct(ok_fecha, n),
        "cliente_correcto": pct(ok_cliente, n),
        "tapados_marcados_dudosos": pct(ocl_dudoso, n_ocl),
        "falsas_alarmas_dudoso": pct(limpios_dudosos, limpios),
        "busqueda": {"exacto": pct(exacto, n), "como_posible": pct(posible, n),
                     "no_encontrado": pct(perdido, n),
                     "no_encontrado_de_los_tapados": f"{perdidos_ocl}/{n_ocl}",
                     "resultados_ajenos_exactos": ajenos},
        "segundos_por_documento_por_nucleo": round(segs * (os.cpu_count() or 1) / n, 2),
    }
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
