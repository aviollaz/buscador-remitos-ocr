"""Ventana para usar el buscador sin consola: buscar con filtros, indexar y exportar a Excel."""

import os
import tempfile
import threading
import time
import tkinter as tk
import traceback
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from . import config
from .busqueda import OPERADORES_MONTO, Filtro, buscar, copiar, leer_lista, nombre_tipo
from .campos import CAMPOS, mostrar, normalizar
from .exportar import a_excel, exportar_indice
from .indice import conectar, indexar, reextraer

TITULO = "Buscador de remitos y facturas"
ULTIMA_CARPETA = os.path.join(config.BASE_DIR, "ultima_carpeta.txt")
MAX_FILAS = 2000                 # en la tabla; el Excel lleva todas
TODOS = "Todos"
MOVIDOS = ("El índice tiene guardada una ubicación vieja (se movieron archivos, se renombró "
           "la carpeta o se borraron). Volvé a indexar la carpeta donde están ahora.")
# Columnas de la tabla: (id, título, ancho en caracteres)
COLUMNAS = ([("buscado", "Buscado", 14), ("resultado", "Resultado", 34)]
            + [(c.nombre, c.etiqueta, c.ancho) for c in CAMPOS] + [("archivo", "Archivo", 24)])


def miles(n):
    return f"{n:,}".replace(",", ".")


def duracion(seg):
    h, m = divmod(int(seg) // 60, 60)
    return f"{h} h {m} min" if h else f"{m} min"


def caja_de_texto(padre, titulo, alto=5):
    marco = ttk.Frame(padre)
    ttk.Label(marco, text=titulo).pack(anchor="w")
    texto = tk.Text(marco, height=alto, width=30)
    texto.pack(fill="both", expand=True)
    return marco, texto


class App:
    def __init__(self, root):
        self.root = root
        root.title(TITULO)
        root.geometry("1250x760")
        if os.name == "nt":
            root.state("zoomed")          # maximizada: la tabla tiene muchas columnas
        root.report_callback_exception = lambda *e: messagebox.showerror(
            "Error", "".join(traceback.format_exception(*e)[-1:]))
        root.protocol("WM_DELETE_WINDOW", self.cerrar)
        f = ttk.Frame(root, padding=10)
        f.pack(fill="both", expand=True)

        # Números y clientes
        cajas = ttk.Frame(f)
        cajas.pack(fill="x")
        m, self.numeros = caja_de_texto(cajas, "Números (uno por renglón; se puede pegar una "
                                               "columna de Excel)")
        m.pack(side="left", fill="both", expand=True)
        ttk.Button(m, text="Cargar números desde Excel…", command=self.cargar_excel).pack(
            anchor="w", pady=(4, 0))
        m, self.clientes = caja_de_texto(cajas, "Clientes: nombre, código o CUIT (uno por "
                                                "renglón)")
        m.pack(side="left", fill="both", expand=True, padx=(10, 0))

        # Filtros
        fl = ttk.Frame(f)
        fl.pack(fill="x", pady=(8, 0))
        self.tipos = {TODOS: None} | {t.nombre: k for k, t in config.CFG.tipos.items()}
        self.tipo = tk.StringVar(value=TODOS)
        self.desde, self.hasta, self.monto, self.texto = (tk.StringVar() for _ in range(4))
        self.monto_op = tk.StringVar()
        self.vinculados = tk.BooleanVar(value=True)
        for etiqueta, widget in (
                ("Tipo", ttk.Combobox(fl, textvariable=self.tipo, values=list(self.tipos),
                                      state="readonly", width=10)),
                ("Fecha desde", ttk.Entry(fl, textvariable=self.desde, width=11)),
                ("hasta", ttk.Entry(fl, textvariable=self.hasta, width=11)),
                ("Monto", ttk.Combobox(fl, textvariable=self.monto_op, state="readonly",
                                       values=("",) + OPERADORES_MONTO, width=3)),
                ("", ttk.Entry(fl, textvariable=self.monto, width=12)),
                ("Contiene el texto", ttk.Entry(fl, textvariable=self.texto, width=20))):
            if etiqueta:
                ttk.Label(fl, text=etiqueta).pack(side="left", padx=(10, 4))
            widget.pack(side="left")
        ttk.Checkbutton(fl, text="Incluir remitos/facturas vinculados",
                        variable=self.vinculados).pack(side="left", padx=(14, 0))
        ttk.Label(f, text="Fechas como dd/mm/aaaa. Monto: elegí <, > o = y escribí el "
                          "importe (por ejemplo 1.234,56).", foreground="gray").pack(anchor="w")

        b = ttk.Frame(f)
        b.pack(fill="x", pady=6)
        for texto, accion in (("Buscar", self.buscar), ("Limpiar", self.limpiar),
                              ("Resultados a Excel", self.a_excel),
                              ("Copiar documentos a una carpeta", self.copiar)):
            ttk.Button(b, text=texto, command=accion).pack(side="left", padx=(0, 6))
        self.cantidad = tk.StringVar()
        ttk.Label(b, textvariable=self.cantidad).pack(side="left", padx=10)

        # Resultados
        t = ttk.Frame(f)
        t.pack(fill="both", expand=True)
        # Los documentos vinculados van "adentro" del que los cita: se despliegan con la flecha
        self.tabla = ttk.Treeview(t, columns=[c for c, _, _ in COLUMNAS], show="tree headings")
        self.tabla.heading("#0", text="Vinculados")
        self.tabla.column("#0", width=110, stretch=False)
        for c, titulo, ancho in COLUMNAS:
            self.tabla.heading(c, text=titulo)
            self.tabla.column(c, width=ancho * 7, stretch=False)
        self.tabla.tag_configure("no", background="#F8D7DA")
        self.tabla.tag_configure("revisar", background="#FFF3CD")
        self.tabla.bind("<Double-1>", self.abrir)
        xs = ttk.Scrollbar(t, orient="horizontal", command=self.tabla.xview)
        ys = ttk.Scrollbar(t, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        ys.pack(side="right", fill="y")
        xs.pack(side="bottom", fill="x")
        self.tabla.pack(fill="both", expand=True)
        ttk.Label(f, text="Doble clic en una fila para abrir el documento.").pack(anchor="w")
        self.resultados = []

        # Índice
        ttk.Separator(f).pack(fill="x", pady=8)
        i = ttk.Frame(f)
        i.pack(fill="x")
        self.boton_indexar = ttk.Button(i, text="Indexar carpeta…", command=self.indexar)
        self.boton_indexar.pack(side="left")
        self.boton_pausar = ttk.Button(i, text="Pausar", command=self.pausar, state="disabled")
        self.boton_pausar.pack(side="left", padx=6)
        ttk.Button(i, text="Exportar índice completo a Excel",
                   command=self.exportar).pack(side="right")
        self.barra = ttk.Progressbar(f)
        self.barra.pack(fill="x", pady=(6, 0))
        self.progreso = tk.StringVar()
        ttk.Label(f, textvariable=self.progreso).pack(anchor="w")
        self.info = tk.StringVar()
        ttk.Label(f, textvariable=self.info).pack(anchor="w")

        self.parar = threading.Event()
        self.avance = None
        # Si cambió config.toml, los datos se recalculan del texto ya leído (sin OCR)
        self.progreso.set("Revisando si hay que actualizar los datos con la configuración…")
        self._en_segundo_plano(self._actualizar_datos)

    # ------------------------------------------------------------ búsqueda

    def filtro(self):
        """Arma el Filtro con lo que hay en la ventana, o avisa qué está mal y devuelve None."""
        ruta = os.path.join(tempfile.gettempdir(), "buscador_numeros.txt")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(self.numeros.get("1.0", "end"))
        fechas = {}
        for nombre, var in (("desde", self.desde), ("hasta", self.hasta)):
            v = var.get().strip()
            fechas[nombre] = normalizar("fecha", v) if v else None
            if v and not fechas[nombre]:
                return self._aviso(f"La fecha '{v}' no es válida. Usá dd/mm/aaaa.")
        op, monto = self.monto_op.get() or None, None
        if op:
            monto = normalizar("monto", self.monto.get())
            if monto is None:
                return self._aviso("Escribí el monto, por ejemplo 1.234,56.")
        filtro = Filtro(
            numeros=leer_lista(ruta), tipo=self.tipos[self.tipo.get()],
            desde=fechas["desde"], hasta=fechas["hasta"], monto_op=op, monto=monto,
            clientes=[c.strip() for c in self.clientes.get("1.0", "end").splitlines()
                      if c.strip()],
            texto=self.texto.get().strip() or None)
        if filtro.vacio():
            return self._aviso("Escribí algún número o elegí algún filtro.")
        return filtro

    def _aviso(self, texto):
        messagebox.showinfo(TITULO, texto)
        return None

    def buscar(self):
        filtro = self.filtro()
        if not filtro:
            return
        self.resultados = buscar(conectar(), filtro, self.vinculados.get())
        self.tabla.delete(*self.tabla.get_children())
        padre, hijos = "", {}
        for n, r in enumerate(self.resultados[:MAX_FILAS]):
            fila = r.fila or {}
            etiqueta = "" if r.vinculado else r.etiqueta    # ya cuelga de su documento
            valores = ["" if r.vinculado else r.buscado, etiqueta]
            valores += [nombre_tipo(fila.get(c.nombre)) if c.nombre == "tipo" and fila
                        else mostrar(c.tipo, fila.get(c.nombre)) for c in CAMPOS]
            valores.append(os.path.basename(fila["ruta"]) if fila else "")
            tags = ("no",) if not r.fila else ("revisar",) if r.revisar else ()
            if r.vinculado:
                hijos[padre] = hijos.get(padre, 0) + 1
            else:
                padre = str(n)
            self.tabla.insert(padre if r.vinculado else "", "end", iid=str(n), values=valores,
                              tags=tags)
        for iid, k in hijos.items():
            self.tabla.item(iid, text=f"{k} vinculado(s)")
            *medio, ultimo = self.tabla.get_children(iid)     # líneas de árbol
            for h in medio:
                self.tabla.item(h, text="├─▸")
            self.tabla.item(ultimo, text="└─▸")
        total = len(self.resultados)
        self.cantidad.set(f"{miles(total)} resultado(s)" + (
            f"; se muestran los primeros {miles(MAX_FILAS)}, el Excel lleva todos"
            if total > MAX_FILAS else ""))

    def cargar_excel(self):
        """Lee los números de la primera columna con datos de un Excel y los busca."""
        ruta = filedialog.askopenfilename(
            title="Excel con los números", filetypes=[("Excel", "*.xlsx *.xlsm"),
                                                      ("Texto", "*.txt *.csv")])
        if not ruta:
            return
        try:
            numeros = leer_lista(ruta)
        except ValueError as e:              # p. ej. un .xls viejo: se explica qué hacer
            messagebox.showwarning(TITULO, str(e))
            return
        self.numeros.delete("1.0", "end")
        self.numeros.insert("1.0", "\n".join(numeros))
        self.buscar()

    def limpiar(self):
        self.numeros.delete("1.0", "end")
        self.clientes.delete("1.0", "end")
        for v in (self.desde, self.hasta, self.monto, self.monto_op, self.texto):
            v.set("")
        self.tipo.set(TODOS)
        self.tabla.delete(*self.tabla.get_children())
        self.resultados = []
        self.cantidad.set("")

    def a_excel(self):
        if not self.resultados:
            return self._aviso("Primero buscá algo.")
        a_excel(self.resultados, abrir=True)

    def copiar(self):
        """Copia los documentos encontrados a Resultados/Encontrados_<fecha> (las
        coincidencias por otro número, como el pedido, en una subcarpeta) y abre la carpeta."""
        rutas = [(r.fila["ruta"], r.secundario) for r in self.resultados if r.fila]
        if not rutas:
            return self._aviso("Primero buscá algo.")
        faltan = {r for r, _ in rutas if not os.path.exists(r)}
        if faltan:
            messagebox.showwarning(TITULO, f"{len(faltan)} documento(s) no se copiaron. "
                                           f"{MOVIDOS}")
        principales = [r for r, sec in rutas if not sec and r not in faltan]
        secundarios = [r for r, sec in rutas if sec and r not in faltan]
        if not principales and not secundarios:
            return
        carpeta = os.path.join(config.SALIDAS, f"Encontrados_{datetime.now():%Y-%m-%d_%H%M%S}")
        copiar(principales, carpeta)
        if secundarios:
            copiar(secundarios, os.path.join(carpeta, "Coincidencias por otro número"))
        os.startfile(carpeta)

    def abrir(self, _evento):
        sel = self.tabla.focus()
        fila = self.resultados[int(sel)].fila if sel else None
        if not fila:
            return
        if not os.path.exists(fila["ruta"]):
            messagebox.showwarning(TITULO, f"No encontré {fila['ruta']}. {MOVIDOS}")
        else:
            os.startfile(fila["ruta"])
        return "break"          # que el doble clic abra el documento sin desplegar la fila

    def exportar(self):
        self.root.config(cursor="watch")
        self.root.update()
        try:
            exportar_indice(abrir=True)
        finally:
            self.root.config(cursor="")

    # ------------------------------------------------------------ indexado

    def actualizar_info(self):
        con = conectar()
        total, parciales = con.execute(
            "SELECT count(*), coalesce(sum(parcial), 0) FROM docs").fetchone()
        por_tipo = ", ".join(f"{nombre_tipo(t)}: {miles(n)}" for t, n in con.execute(
            "SELECT tipo, count(*) FROM docs GROUP BY tipo ORDER BY tipo"))
        extra = f"; {miles(parciales)} todavía sin texto completo" if parciales else ""
        self.info.set(f"{miles(total)} documentos en el índice"
                      f"{f' ({por_tipo})' if por_tipo else ''}{extra}.")

    def _en_segundo_plano(self, tarea, *args):
        self.boton_indexar["state"] = "disabled"
        self.hilo = threading.Thread(target=tarea, args=args, daemon=True)
        self.hilo.start()
        self.root.after(300, self.mirar)

    def _actualizar_datos(self):
        try:
            n = reextraer(conectar())
            self.fin = (f"Se actualizaron los datos de {miles(n)} documentos con la "
                        "configuración actual (sin volver a leerlos)." if n else "")
        except Exception as e:  # noqa: BLE001
            self.fin = f"Error al actualizar los datos: {e}"

    def indexar(self):
        inicial = None
        if os.path.exists(ULTIMA_CARPETA):
            with open(ULTIMA_CARPETA, encoding="utf-8") as fh:
                inicial = fh.read().strip()
        carpeta = filedialog.askdirectory(title="Carpeta de los documentos",
                                          initialdir=inicial)
        if not carpeta:
            return
        with open(ULTIMA_CARPETA, "w", encoding="utf-8") as fh:
            fh.write(carpeta)
        self.parar.clear()
        self.avance = self.paso = None
        self.progreso.set("Buscando archivos en la carpeta…")
        self.boton_pausar["state"] = "normal"
        self._en_segundo_plano(self._indexar, carpeta)

    def _indexar(self, carpeta):
        try:
            indexar(carpeta, avance=self._avance, parar=self.parar.is_set)
            self.fin = ("Pausado. La próxima vez sigue donde quedó." if self.parar.is_set()
                        else "Indexado completo.")
        except BaseException as e:  # noqa: BLE001 - incluye sys.exit con el mensaje de error
            self.fin = f"Error: {e}"

    def _avance(self, paso, i, total):        # corre en el hilo del indexado
        if paso != self.paso:
            self.paso, self.t0 = paso, time.time()
        self.avance = (paso, i, total, time.time() - self.t0)

    def mirar(self):
        if self.avance and not self.parar.is_set():
            paso, i, total, seg = self.avance
            self.barra["maximum"], self.barra["value"] = total, i
            que = ("lectura rápida (lo leído ya se puede buscar)" if paso == 1
                   else "texto completo de la página")
            self.progreso.set(f"Paso {paso} de 2, {que}: {miles(i)} de {miles(total)}, "
                              f"faltan ~{duracion(seg / i * (total - i))}")
        self.actualizar_info()
        if self.hilo.is_alive():
            self.root.after(1000, self.mirar)
            return
        self.progreso.set(self.fin)
        self.barra["value"] = 0
        self.boton_indexar["state"] = "normal"
        self.boton_pausar["state"] = "disabled"

    def pausar(self):
        self.parar.set()
        self.boton_pausar["state"] = "disabled"
        self.progreso.set("Pausando… (termina los archivos que está leyendo)")

    def cerrar(self):
        if self.hilo.is_alive() and self.boton_pausar["state"] == "normal":
            if not messagebox.askyesno(TITULO, "Se está indexando. ¿Pausar y salir? La "
                                               "próxima vez sigue donde quedó."):
                return
            self.pausar()
        self._esperar_y_cerrar()

    def _esperar_y_cerrar(self):
        if self.hilo.is_alive():
            self.root.after(300, self._esperar_y_cerrar)
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
