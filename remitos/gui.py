"""Ventana para usar el buscador sin consola: buscar, indexar y exportar a Excel."""

import os
import tempfile
import threading
import time
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

from . import config
from .busqueda import buscar_lista, cargar, leer_lista, parsear_consulta, resolver
from .exportar import exportar_excel
from .indice import conectar, indexar

ULTIMA_CARPETA = os.path.join(config.BASE_DIR, "ultima_carpeta.txt")
COLUMNAS = ("Buscado", "Resultado", "Remito", "Fecha", "Cliente", "Pedido", "Archivo")


def miles(n):
    return f"{n:,}".replace(",", ".")


def duracion(seg):
    h, m = divmod(int(seg) // 60, 60)
    return f"{h} h {m} min" if h else f"{m} min"


class App:
    def __init__(self, root):
        self.root = root
        root.title("Buscador de remitos")
        root.geometry("1050x680")
        root.report_callback_exception = lambda *e: messagebox.showerror(
            "Error", "".join(traceback.format_exception(*e)[-1:]))
        root.protocol("WM_DELETE_WINDOW", self.cerrar)
        f = ttk.Frame(root, padding=10)
        f.pack(fill="both", expand=True)

        # Búsqueda
        t = ttk.Frame(f)
        t.pack(fill="x", pady=(0, 4))
        ttk.Label(t, text="Pegá uno o varios números de remito "
                          "(podés copiar una columna entera de Excel), o").pack(side="left")
        ttk.Button(t, text="Cargar desde Excel…", command=self.cargar_excel).pack(
            side="left", padx=6)
        self.entrada = tk.Text(f, height=5)
        self.entrada.pack(fill="x")
        b = ttk.Frame(f)
        b.pack(fill="x", pady=6)
        ttk.Button(b, text="Buscar", command=self.buscar).pack(side="left")
        ttk.Button(b, text="Resultados a Excel", command=self.a_excel).pack(side="left", padx=6)
        self.copiar = tk.BooleanVar()
        ttk.Checkbutton(b, text="Copiar también los remitos encontrados a una carpeta",
                        variable=self.copiar).pack(side="left")

        self.tabla = ttk.Treeview(f, columns=COLUMNAS + ("ruta",), displaycolumns=COLUMNAS,
                                  show="headings")
        for c, ancho in zip(COLUMNAS, (120, 150, 130, 85, 250, 130, 180)):
            self.tabla.heading(c, text=c)
            self.tabla.column(c, width=ancho)
        self.tabla.tag_configure("no", background="#F8D7DA")
        self.tabla.tag_configure("revisar", background="#FFF3CD")
        self.tabla.bind("<Double-1>", self.abrir)
        self.tabla.pack(fill="both", expand=True)
        ttk.Label(f, text="Doble clic en una fila para abrir el remito.").pack(anchor="w")

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

        self.hilo = None
        self.parar = threading.Event()
        self.actualizar_info()

    # ------------------------------------------------------------ búsqueda

    def consultas(self):
        """Pasa lo pegado a un .txt y lo lee igual que una lista (mismas reglas que la consola)."""
        ruta = os.path.join(tempfile.gettempdir(), "remitos_lista.txt")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(self.entrada.get("1.0", "end"))
        return ruta, leer_lista(ruta)

    def cargar_excel(self):
        """Lee los números de la primera columna con datos (igual que antes) y los busca."""
        ruta = filedialog.askopenfilename(
            title="Excel con los números de remito",
            filetypes=[("Excel", "*.xlsx *.xlsm"), ("Texto", "*.txt *.csv")])
        if not ruta:
            return
        try:
            numeros = leer_lista(ruta)
        except SystemExit as e:              # p. ej. un .xls viejo: se explica qué hacer
            messagebox.showwarning("Buscador de remitos", str(e))
            return
        self.entrada.delete("1.0", "end")
        self.entrada.insert("1.0", "\n".join(numeros))
        self.buscar()

    def buscar(self):
        _, consultas = self.consultas()
        self.tabla.delete(*self.tabla.get_children())
        con = conectar()
        todas, dudosos = cargar(con)
        for q in consultas:
            c = parsear_consulta(q)
            por_remito, posibles, por_pedido = (resolver(con, todas, dudosos, c, q)
                                                if c else ([], [], []))
            filas = ([("Encontrado", r, ()) for r in por_remito]
                     + [("Posible (revisar)", r, ("revisar",)) for r in posibles])
            filas += [("Por pedido" if filas else "Solo por pedido (revisar)", r,
                       () if filas else ("revisar",)) for r in por_pedido]
            if not filas:
                self.tabla.insert("", "end", values=(q, "NO ENCONTRADO"), tags=("no",))
            for etiqueta, (ruta, remito, pedido, fecha, cliente), tags in filas:
                self.tabla.insert("", "end", tags=tags, values=(
                    q, etiqueta, remito, fecha, cliente, pedido, os.path.basename(ruta), ruta))

    def a_excel(self):
        ruta, consultas = self.consultas()
        if not consultas:
            messagebox.showinfo("Buscador de remitos", "Primero pegá algún número.")
            return
        buscar_lista(ruta, "auto", "auto" if self.copiar.get() else None, abrir=True)

    def abrir(self, _evento):
        ruta = self.tabla.set(self.tabla.focus(), "ruta")
        if ruta:
            os.startfile(ruta)

    def exportar(self):
        self.root.config(cursor="watch")
        self.root.update()
        try:
            exportar_excel(abrir=True)
        finally:
            self.root.config(cursor="")

    # ------------------------------------------------------------ indexado

    def actualizar_info(self):
        total, parciales = conectar().execute(
            "SELECT count(*), coalesce(sum(parcial), 0) FROM docs").fetchone()
        extra = f" ({miles(parciales)} todavía sin texto completo)" if parciales else ""
        self.info.set(f"{miles(total)} remitos en el índice{extra}.")

    def indexar(self):
        inicial = None
        if os.path.exists(ULTIMA_CARPETA):
            with open(ULTIMA_CARPETA, encoding="utf-8") as fh:
                inicial = fh.read().strip()
        carpeta = filedialog.askdirectory(title="Carpeta de los remitos", initialdir=inicial)
        if not carpeta:
            return
        with open(ULTIMA_CARPETA, "w", encoding="utf-8") as fh:
            fh.write(carpeta)
        self.parar.clear()
        self.avance = self.paso = None
        self.progreso.set("Buscando archivos en la carpeta…")
        self.boton_indexar["state"] = "disabled"
        self.boton_pausar["state"] = "normal"
        self.hilo = threading.Thread(target=self._indexar, args=(carpeta,), daemon=True)
        self.hilo.start()
        self.root.after(500, self.mirar)

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
        if self.hilo and self.hilo.is_alive():
            if not messagebox.askyesno("Buscador de remitos", "Se está indexando. ¿Pausar y "
                                       "salir? La próxima vez sigue donde quedó."):
                return
            self.pausar()
            self._esperar_y_cerrar()
        else:
            self.root.destroy()

    def _esperar_y_cerrar(self):
        if self.hilo.is_alive():
            self.root.after(300, self._esperar_y_cerrar)
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
