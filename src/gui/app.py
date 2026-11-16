"""Ventana principal de MiFactura."""

import logging
import os
import queue
import threading
from tkinter import messagebox

import ttkbootstrap as ttk

from config import ICON_PATH, is_configured, is_debug
from gui.dialogs import HistoryDialog, SettingsDialog
from models.database import CONDICIONES_IVA, guardar_factura
from services.facturacion import (
    FacturacionError,
    descripcion_comprobante,
    emitir_factura,
    motor,
)
from utils.formato import (
    cuit_valido,
    formatear_cuit,
    formatear_pesos,
    numero_a_texto,
    parsear_numero,
    solo_digitos,
)

logger = logging.getLogger(__name__)

PREAJUSTES_PRODUCTOS = [
    "Fotos Carnet",
    "Revelado de Fotos",
    "Servicio Laser",
    "Estampados",
]

TIPOS_POR_CONDICION = {
    CONDICIONES_IVA[0]: ("DNI", "CUIT", "CUIL"),
    CONDICIONES_IVA[1]: ("CUIT",),
    CONDICIONES_IVA[2]: ("CUIT",),
}

FUENTE_MARCA = ("Segoe UI Semibold", 17)
FUENTE_SECCION = ("Segoe UI Semibold", 11)
FUENTE_AYUDA = ("Segoe UI", 9)
FUENTE_TOTAL = ("Segoe UI Semibold", 24)
FUENTE_BOTON = ("Segoe UI Semibold", 12)


class App:
    # pylint: disable=too-many-instance-attributes
    """Interfaz principal: armado de la factura y emisión en segundo plano."""

    def __init__(self, root):
        self.root = root
        self.items = {}  # iid de la tabla -> (descripción, cantidad, precio)
        self.eventos = queue.Queue()
        self.ocupado = False
        self._formateando = False

        root.title("MiFactura")
        try:
            root.iconbitmap(ICON_PATH)
        except Exception:  # pylint: disable=broad-except
            pass
        self._crear_encabezado()
        self._crear_estado()
        self._crear_cuerpo()
        estilo = ttk.Style()
        estilo.configure(self.boton_emitir.cget("style"), font=FUENTE_BOTON)
        estilo.configure("Treeview", rowheight=self._px(30))

        # El tamaño sale del contenido, así se ve bien con cualquier escala de Windows.
        root.update_idletasks()
        ancho = max(root.winfo_reqwidth(), self._px(980))
        alto = max(root.winfo_reqheight(), self._px(620))
        root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())
        self._centrar(ancho, alto)

        self._al_cambiar_condicion()
        self._actualizar_total()
        self.descripcion.focus_set()

    # ------------------------------------------------------------------ UI

    def _px(self, valor):
        """Convierte píxeles de diseño (96 dpi) a píxeles reales de pantalla."""
        return round(valor * self.root.winfo_fpixels("1i") / 96)

    def _centrar(self, ancho, alto):
        x = (self.root.winfo_screenwidth() - ancho) // 2
        y = (self.root.winfo_screenheight() - alto) // 3
        self.root.geometry(f"{ancho}x{alto}+{x}+{max(y, 0)}")

    def _crear_encabezado(self):
        barra = ttk.Frame(self.root, bootstyle="primary", padding=(24, 14))
        barra.pack(fill="x")

        marca = ttk.Frame(barra, bootstyle="primary")
        marca.pack(side="left")
        ttk.Label(
            marca, text="MiFactura", font=FUENTE_MARCA, bootstyle="inverse-primary"
        ).pack(anchor="w")
        ttk.Label(
            marca,
            text="Facturación electrónica ARCA",
            font=FUENTE_AYUDA,
            bootstyle="inverse-primary",
        ).pack(anchor="w")

        ttk.Button(
            barra,
            text="Configuración",
            bootstyle="primary",
            command=self.abrir_configuracion,
        ).pack(side="right")
        ttk.Button(
            barra, text="Historial", bootstyle="primary", command=self.abrir_historial
        ).pack(side="right", padx=4)

    def _crear_estado(self):
        pie = ttk.Frame(self.root)
        pie.pack(side="bottom", fill="x")
        ttk.Separator(pie).pack(fill="x")
        fila = ttk.Frame(pie, padding=(24, 8))
        fila.pack(fill="x")
        self.estado = ttk.Label(fila, text="", bootstyle="secondary")
        self.estado.pack(side="left")
        self.progreso = ttk.Progressbar(
            fila, maximum=100, length=240, bootstyle="success-striped"
        )
        self._estado("Listo para facturar.")

    def _crear_cuerpo(self):
        cuerpo = ttk.Frame(self.root, padding=(24, 20, 24, 16))
        cuerpo.pack(fill="both", expand=True)
        cuerpo.columnconfigure(1, weight=1)
        cuerpo.rowconfigure(0, weight=1)

        izquierda = ttk.Frame(cuerpo, width=300)
        izquierda.grid(row=0, column=0, sticky="ns", padx=(0, 24))
        self._crear_cliente(izquierda)
        ttk.Separator(izquierda).pack(fill="x", pady=18)
        self._crear_producto(izquierda)

        derecha = ttk.Frame(cuerpo)
        derecha.grid(row=0, column=1, sticky="nsew")
        self._crear_detalle(derecha)

    def _crear_cliente(self, padre):
        ttk.Label(padre, text="Cliente", font=FUENTE_SECCION).pack(anchor="w")

        ttk.Label(padre, text="Condición frente al IVA").pack(anchor="w", pady=(10, 4))
        self.condicion = ttk.Combobox(
            padre, values=CONDICIONES_IVA, state="readonly", width=34
        )
        self.condicion.set(CONDICIONES_IVA[0])
        self.condicion.pack(fill="x")
        self.condicion.bind("<<ComboboxSelected>>", self._al_cambiar_condicion)

        ttk.Label(padre, text="Documento").pack(anchor="w", pady=(12, 4))
        fila = ttk.Frame(padre)
        fila.pack(fill="x")
        self.tipo_documento = ttk.Combobox(fila, state="readonly", width=6)
        self.tipo_documento.pack(side="left")
        self.tipo_documento.bind("<<ComboboxSelected>>", self._formatear_documento)

        self.documento_var = ttk.StringVar()
        self.documento_var.trace_add("write", self._formatear_documento)
        self.documento = ttk.Entry(fila, textvariable=self.documento_var)
        self.documento.pack(side="left", fill="x", expand=True, padx=(8, 0))

        self.ayuda_documento = ttk.Label(
            padre, text="", bootstyle="secondary", font=FUENTE_AYUDA
        )
        self.ayuda_documento.pack(anchor="w", pady=(4, 0))

    def _crear_producto(self, padre):
        ttk.Label(padre, text="Agregar producto", font=FUENTE_SECCION).pack(anchor="w")

        ttk.Label(padre, text="Descripción").pack(anchor="w", pady=(10, 4))
        self.descripcion = ttk.Combobox(padre, values=PREAJUSTES_PRODUCTOS)
        self.descripcion.pack(fill="x")

        fila = ttk.Frame(padre)
        fila.pack(fill="x", pady=(12, 0))
        fila.columnconfigure((0, 1), weight=1, uniform="campo")
        ttk.Label(fila, text="Cantidad").grid(row=0, column=0, sticky="w")
        ttk.Label(fila, text="Precio unitario ($)").grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )
        self.cantidad = ttk.Entry(fila, width=10, justify="right")
        self.cantidad.insert(0, "1")
        self.cantidad.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.precio = ttk.Entry(fila, width=10, justify="right")
        self.precio.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(4, 0))

        ttk.Button(
            padre,
            text="Agregar a la factura",
            bootstyle="primary-outline",
            command=self.agregar_producto,
        ).pack(fill="x", pady=(16, 0))

        for campo in (self.descripcion, self.cantidad, self.precio):
            campo.bind("<Return>", lambda _e: self.agregar_producto())

    def _crear_detalle(self, padre):
        padre.columnconfigure(0, weight=1)
        padre.rowconfigure(1, weight=1)

        encabezado = ttk.Frame(padre)
        encabezado.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(encabezado, text="Detalle de la factura", font=FUENTE_SECCION).pack(
            side="left"
        )
        self.contador = ttk.Label(encabezado, text="", bootstyle="secondary")
        self.contador.pack(side="left", padx=10)
        self.boton_vaciar = ttk.Button(
            encabezado,
            text="Vaciar",
            bootstyle="secondary-link",
            command=self.vaciar,
        )
        self.boton_vaciar.pack(side="right")
        self.boton_quitar = ttk.Button(
            encabezado,
            text="Quitar seleccionados",
            bootstyle="danger-link",
            command=self.quitar_seleccionados,
        )
        self.boton_quitar.pack(side="right")

        columnas = (
            ("descripcion", "Descripción", 220, "w"),
            ("cantidad", "Cantidad", 80, "e"),
            ("precio", "Precio unitario", 120, "e"),
            ("subtotal", "Subtotal", 120, "e"),
        )
        self.tabla = ttk.Treeview(
            padre, columns=[c[0] for c in columnas], show="headings", height=8
        )
        for clave, titulo, ancho, alineacion in columnas:
            self.tabla.heading(clave, text=titulo, anchor=alineacion)
            self.tabla.column(
                clave,
                width=self._px(ancho),
                minwidth=self._px(80),
                anchor=alineacion,
                stretch=clave == "descripcion",
            )
        barra = ttk.Scrollbar(
            padre, orient="vertical", command=self.tabla.yview, bootstyle="round"
        )
        self.tabla.configure(yscrollcommand=barra.set)
        self.tabla.grid(row=1, column=0, sticky="nsew")
        barra.grid(row=1, column=1, sticky="ns")
        self.tabla.bind("<Delete>", lambda _e: self.quitar_seleccionados())

        pie = ttk.Frame(padre)
        pie.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        totales = ttk.Frame(pie)
        totales.pack(side="left")
        ttk.Label(
            totales, text="TOTAL", bootstyle="secondary", font=FUENTE_AYUDA
        ).pack(anchor="w")
        self.total = ttk.Label(totales, text="", font=FUENTE_TOTAL)
        self.total.pack(anchor="w")

        self.boton_emitir = ttk.Button(
            pie,
            text="Emitir factura",
            bootstyle="success",
            padding=(36, 14),
            command=self.emitir,
        )
        self.boton_emitir.pack(side="right", anchor="s")

    # ------------------------------------------------------------- Estado

    def _estado(self, texto, tipo="secondary"):
        self.estado.configure(text=texto, bootstyle=tipo)

    def _error(self, texto, campo=None):
        self._estado(texto, "danger")
        self.root.bell()
        if campo is not None:
            campo.focus_set()

    def _bloquear(self, ocupado):
        self.ocupado = ocupado
        estado = "disabled" if ocupado else "normal"
        for boton in (self.boton_emitir, self.boton_quitar, self.boton_vaciar):
            boton.configure(state=estado)
        self.boton_emitir.configure(
            text="Emitiendo…" if ocupado else "Emitir factura"
        )
        if ocupado:
            self.progreso.configure(value=0)
            self.progreso.pack(side="right")
        else:
            self.progreso.pack_forget()

    # ------------------------------------------------------------ Cliente

    def _al_cambiar_condicion(self, _evento=None):
        tipos = TIPOS_POR_CONDICION[self.condicion.get()]
        self.tipo_documento.configure(values=tipos)
        if self.tipo_documento.get() not in tipos:
            self.tipo_documento.set(tipos[0])
        obligatorio = self.condicion.get() != CONDICIONES_IVA[0]
        self.ayuda_documento.configure(
            text="Obligatorio para esta condición."
            if obligatorio
            else "Opcional para consumidor final."
        )
        self._formatear_documento()

    def _formatear_documento(self, *_args):
        # Se difiere: cambiar la variable dentro de su propio trace deja al
        # Entry mostrando el valor viejo.
        if not self._formateando:
            self._formateando = True
            self.root.after_idle(self._aplicar_formato)

    def _aplicar_formato(self):
        digitos = solo_digitos(self.documento_var.get())
        if self.tipo_documento.get() == "DNI":
            texto = digitos[:8]
        else:
            texto = formatear_cuit(digitos)
        if texto != self.documento_var.get():
            self.documento_var.set(texto)
            self.documento.icursor("end")
        self._formateando = False

    def _validar_cliente(self):
        """Devuelve (tipo, número) o None si hay un error (ya informado)."""
        tipo = self.tipo_documento.get()
        numero = solo_digitos(self.documento_var.get())
        obligatorio = self.condicion.get() != CONDICIONES_IVA[0]

        if not numero:
            if obligatorio:
                self._error("Ingresá el CUIT del cliente.", self.documento)
                return None
            return tipo, ""
        if tipo == "DNI":
            if len(numero) not in (7, 8):
                self._error("El DNI debe tener 7 u 8 dígitos.", self.documento)
                return None
        elif not cuit_valido(numero):
            self._error(f"El {tipo} del cliente no es válido.", self.documento)
            return None
        return tipo, numero

    # ---------------------------------------------------------- Productos

    def agregar_producto(self):
        """Agrega a la tabla el producto cargado en el formulario."""
        descripcion = self.descripcion.get().strip()
        if not descripcion:
            self._error("Escribí la descripción del producto.", self.descripcion)
            return
        try:
            cantidad = parsear_numero(self.cantidad.get())
            if cantidad <= 0:
                raise ValueError
        except ValueError:
            self._error("La cantidad debe ser un número mayor a cero.", self.cantidad)
            return
        try:
            precio = parsear_numero(self.precio.get())
            if precio <= 0:
                raise ValueError
        except ValueError:
            self._error("El precio debe ser un número mayor a cero.", self.precio)
            return

        iid = self.tabla.insert(
            "",
            "end",
            values=(
                descripcion,
                numero_a_texto(cantidad),
                formatear_pesos(precio),
                formatear_pesos(cantidad * precio),
            ),
        )
        self.items[iid] = (descripcion, cantidad, precio)
        self.tabla.see(iid)

        self.descripcion.set("")
        self.cantidad.delete(0, "end")
        self.cantidad.insert(0, "1")
        self.precio.delete(0, "end")
        self.descripcion.focus_set()
        self._estado("Producto agregado.")
        self._actualizar_total()

    def quitar_seleccionados(self):
        """Quita de la factura las filas seleccionadas."""
        if self.ocupado:
            return
        seleccion = self.tabla.selection()
        if not seleccion:
            self._estado("Seleccioná una fila de la tabla para quitarla.")
            return
        for iid in seleccion:
            self.tabla.delete(iid)
            self.items.pop(iid, None)
        self._actualizar_total()

    def vaciar(self):
        """Quita todos los productos de la factura."""
        self.tabla.delete(*self.tabla.get_children())
        self.items.clear()
        self._actualizar_total()

    def _total(self):
        return sum(cantidad * precio for _, cantidad, precio in self.items.values())

    def _actualizar_total(self):
        self.total.configure(text=formatear_pesos(self._total()))
        cantidad = len(self.items)
        self.contador.configure(
            text="" if not cantidad else f"{cantidad} ítem{'s' if cantidad > 1 else ''}"
        )

    def _limpiar(self):
        self.vaciar()
        self.documento_var.set("")
        self.condicion.set(CONDICIONES_IVA[0])
        self._al_cambiar_condicion()

    # ------------------------------------------------------------ Diálogos

    def abrir_configuracion(self):
        """Abre la configuración de la cuenta."""
        if self.ocupado:
            return
        dialogo = SettingsDialog(self.root)
        self.root.wait_window(dialogo)
        if dialogo.guardado:
            self._estado("Configuración guardada.", "success")

    def abrir_historial(self):
        """Abre el historial de facturas emitidas."""
        self.root.wait_window(HistoryDialog(self.root))

    # ------------------------------------------------------------- Emisión

    def emitir(self):
        """Valida los datos y emite la factura en segundo plano."""
        if self.ocupado:
            return
        cliente = self._validar_cliente()
        if cliente is None:
            return
        if not self.items:
            self._error("Agregá al menos un producto a la factura.", self.descripcion)
            return
        if not is_configured():
            self._error("Falta completar la configuración de ARCA.")
            self.abrir_configuracion()
            return

        tipo, numero = cliente
        condicion = self.condicion.get()
        total = self._total()
        destinatario = f"{tipo} {self.documento_var.get()}" if numero else "sin identificar"
        simulacion = "\n\n(Modo DEBUG: no se confirmará en ARCA.)" if is_debug() else ""
        if not messagebox.askokcancel(
            "Emitir factura",
            f"Se va a emitir una factura por {formatear_pesos(total)}\n"
            f"{descripcion_comprobante(condicion)}\n"
            f"{condicion} · Cliente {destinatario}\n"
            f"{len(self.items)} ítem(s)\n\n"
            "Una vez emitida no se puede deshacer. ¿Continuar?" + simulacion,
            parent=self.root,
        ):
            return

        productos = [
            {
                "Product": descripcion,
                "Quantity": numero_a_texto(cantidad),
                "Price": numero_a_texto(precio),
            }
            for descripcion, cantidad, precio in self.items.values()
        ]
        datos = {
            "tipo": tipo,
            "numero": numero,
            "condicion": condicion,
            "productos": productos,
            "total": total,
        }

        self._bloquear(True)
        self._estado("Conectando con ARCA…")
        threading.Thread(target=self._trabajar, args=(datos,), daemon=True).start()
        self.root.after(100, self._atender_eventos, datos)

    def _trabajar(self, datos):
        """Hilo de trabajo: nunca toca widgets, solo publica eventos."""
        try:
            resultado = emitir_factura(
                datos["tipo"],
                datos["numero"],
                datos["condicion"],
                datos["productos"],
                on_progress=lambda p, m: self.eventos.put(("progreso", (p, m))),
            )
            self.eventos.put(("fin", resultado))
        except FacturacionError as error:
            self.eventos.put(("error", str(error)))
        except Exception as error:  # pylint: disable=broad-except
            logger.exception("Error inesperado al emitir")
            self.eventos.put(("error", f"Error inesperado: {error}"))

    def _atender_eventos(self, datos):
        try:
            while True:
                tipo, valor = self.eventos.get_nowait()
                if tipo == "progreso":
                    self.progreso.configure(value=valor[0])
                    self._estado(f"{valor[1]}…")
                elif tipo == "fin":
                    self._al_terminar(datos, valor)
                    return
                else:
                    self._bloquear(False)
                    self._estado("No se pudo emitir la factura.", "danger")
                    messagebox.showerror(
                        "No se pudo emitir", valor, parent=self.root
                    )
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._atender_eventos, datos)

    def _al_terminar(self, datos, resultado):
        self._bloquear(False)
        if not resultado["emitida"]:
            self._estado("Simulación terminada: la factura no se confirmó.", "info")
            return

        try:
            guardar_factura(
                datos["numero"],
                datos["tipo"],
                datos["condicion"],
                datos["productos"],
                datos["total"],
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception("La factura se emitió pero no se guardó en el historial")

        self._limpiar()
        pdf = resultado["pdf"]
        detalle = resultado.get("detalle")
        encabezado = f"{detalle}\n\n" if detalle else ""
        if pdf:
            self._estado(f"Factura emitida · {detalle or pdf.name}", "success")
            if messagebox.askyesno(
                "Factura emitida",
                f"{encabezado}La factura se emitió y se guardó en:\n{pdf}\n\n"
                "¿Abrir el PDF?",
                parent=self.root,
            ):
                os.startfile(pdf)  # pylint: disable=no-member
        else:
            self._estado(f"Factura emitida sin PDF. {detalle or ''}", "warning")
            messagebox.showwarning(
                "Factura emitida",
                f"{encabezado}La factura se emitió, pero no se pudo guardar el PDF.\n"
                + (
                    "Los datos quedaron registrados en logs/app.log."
                    if motor() == "api"
                    else "Podés descargarlo desde «Consultas» en Comprobantes en línea."
                ),
                parent=self.root,
            )
