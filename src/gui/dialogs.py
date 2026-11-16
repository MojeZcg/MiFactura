"""Ventanas secundarias: configuración e historial."""

import os
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk

from config import DEFAULT_DOWNLOAD_PATH, ICON_PATH, save_settings
from models.database import listar_facturas
from models.downloads import exportar_historial
from utils.formato import cuit_valido, formatear_cuit, formatear_pesos, solo_digitos

FUENTE_TITULO = ("Segoe UI Semibold", 15)
FUENTE_AYUDA = ("Segoe UI", 9)


def _preparar(ventana, parent, titulo):
    """Título, ícono y modalidad comunes a los diálogos."""
    ventana.title(titulo)
    try:
        ventana.iconbitmap(ICON_PATH)
    except Exception:  # pylint: disable=broad-except
        pass
    if parent.winfo_viewable():
        ventana.transient(parent)


def _centrar(ventana):
    ventana.update_idletasks()
    ancho, alto = ventana.winfo_reqwidth(), ventana.winfo_reqheight()
    x = (ventana.winfo_screenwidth() - ancho) // 2
    y = (ventana.winfo_screenheight() - alto) // 3
    ventana.geometry(f"+{x}+{y}")


MOTORES = {
    "web": "Navegador automático (Comprobantes en línea)",
    "api": "API de ARCA (web service, con certificado)",
}
CONDICIONES_EMISOR = {
    "monotributo": "Monotributista (Factura C)",
    "ri": "Resp. Inscripto (Factura A / B)",
}
AMBIENTES = {
    "produccion": "Producción (facturas reales)",
    "homologacion": "Homologación (pruebas)",
}
ALICUOTAS = ("21", "10.5", "27")
PASOS_CERTIFICADO = (
    "Se crearon dos archivos en:\n{carpeta}\n\n"
    "1. Entrá a ARCA con clave fiscal → «Administración de Certificados "
    "Digitales» → agregá un alias y subí el archivo .csr.\n"
    "2. Descargá el certificado (.crt) y elegilo acá en «Certificado».\n"
    "3. En «Administrador de Relaciones» asociá el servicio «Facturación "
    "Electrónica» (wsfe) a ese certificado.\n"
    "4. En «Administración de puntos de venta y domicilios» creá un punto de "
    "venta de tipo «RECE para aplicativo y web services».\n\n"
    "No borres ni compartas el archivo .key: es tu clave privada."
)


def _clave_de(opciones, texto):
    """Clave de un dict de opciones a partir del texto mostrado."""
    return next(clave for clave, valor in opciones.items() if valor == texto)


class SettingsDialog(ttk.Toplevel):
    # pylint: disable=too-many-instance-attributes
    """Configuración de la cuenta de ARCA, el motor de facturación y el emisor."""

    def __init__(self, parent, primera_vez=False):
        super().__init__(parent)
        _preparar(self, parent, "Configuración · MiFactura")
        self.resizable(False, False)
        self.guardado = False
        self._tiene_clave = bool(os.getenv("ARCA_KEY"))

        cuerpo = ttk.Frame(self, padding=24)
        cuerpo.pack(fill="both", expand=True)

        titulo = "Bienvenido a MiFactura" if primera_vez else "Configuración"
        ttk.Label(cuerpo, text=titulo, font=FUENTE_TITULO).pack(anchor="w")
        ttk.Label(
            cuerpo,
            text="Estos datos se guardan solo en esta computadora.",
            bootstyle="secondary",
            font=FUENTE_AYUDA,
        ).pack(anchor="w", pady=(2, 14))

        self.pestanas = ttk.Notebook(cuerpo)
        self.pestanas.pack(fill="both", expand=True)
        self._crear_general()
        self._crear_api()
        self._crear_emisor()

        botones = ttk.Frame(cuerpo)
        botones.pack(anchor="e", pady=(20, 0))
        ttk.Button(
            botones,
            text="Salir" if primera_vez else "Cancelar",
            bootstyle="secondary-link",
            command=self.destroy,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            botones, text="Guardar", bootstyle="primary", width=14, command=self._guardar
        ).pack(side="left")

        self.bind("<Escape>", lambda _e: self.destroy())
        _centrar(self)
        self.cuil.focus_set()
        self.grab_set()

    # ------------------------------------------------------------ Pestañas

    def _pestana(self, titulo):
        marco = ttk.Frame(self.pestanas, padding=18)
        marco.columnconfigure(0, weight=1)
        self.pestanas.add(marco, text=titulo)
        return marco

    @staticmethod
    def _campo(padre, fila, etiqueta, valor="", ayuda=None, **opciones):
        """Etiqueta + Entry (+ ayuda). Devuelve el Entry."""
        ttk.Label(padre, text=etiqueta).grid(
            row=fila, column=0, columnspan=2, sticky="w"
        )
        entrada = ttk.Entry(padre, width=48, **opciones)
        entrada.insert(0, valor)
        entrada.grid(
            row=fila + 1, column=0, columnspan=2, sticky="ew", pady=(4, 2 if ayuda else 12)
        )
        if ayuda:
            ttk.Label(padre, text=ayuda, bootstyle="secondary", font=FUENTE_AYUDA).grid(
                row=fila + 2, column=0, columnspan=2, sticky="w", pady=(0, 12)
            )
        return entrada

    @staticmethod
    def _lista(padre, fila, columna, etiqueta, opciones, actual):
        ttk.Label(padre, text=etiqueta).grid(
            row=fila, column=columna, sticky="w", padx=(0 if columna == 0 else 8, 0)
        )
        lista = ttk.Combobox(padre, values=list(opciones), state="readonly", width=30)
        lista.set(actual)
        lista.grid(
            row=fila + 1,
            column=columna,
            sticky="ew",
            pady=(4, 12),
            padx=(0 if columna == 0 else 8, 0),
        )
        return lista

    def _archivo(self, padre, fila, etiqueta, valor, tipos):
        ttk.Label(padre, text=etiqueta).grid(
            row=fila, column=0, columnspan=2, sticky="w"
        )
        variable = ttk.StringVar(value=valor)
        ttk.Entry(padre, textvariable=variable).grid(
            row=fila + 1, column=0, sticky="ew", pady=(4, 12)
        )

        def elegir():
            ruta = filedialog.askopenfilename(
                parent=self, title=etiqueta, filetypes=tipos
            )
            if ruta:
                variable.set(ruta)

        ttk.Button(
            padre, text="Examinar…", bootstyle="secondary-outline", command=elegir
        ).grid(row=fila + 1, column=1, padx=(8, 0), pady=(4, 12))
        return variable

    def _crear_general(self):
        marco = self._pestana("General")

        ttk.Label(marco, text="Cómo emitir las facturas").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        self.motor = ttk.StringVar(
            value="api" if os.getenv("ARCA_MOTOR") == "api" else "web"
        )
        for indice, (clave, texto) in enumerate(MOTORES.items()):
            ttk.Radiobutton(
                marco, text=texto, value=clave, variable=self.motor
            ).grid(row=1 + indice, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(
            marco,
            text="La API es más rápida y estable, pero requiere completar la "
            "pestaña «API de ARCA».",
            bootstyle="secondary",
            font=FUENTE_AYUDA,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 14))

        self.cuil = self._campo(
            marco, 4, "CUIT", formatear_cuit(solo_digitos(os.getenv("ARCA_CUIL", "")))
        )
        self.clave = self._campo(
            marco,
            6,
            "Clave fiscal (solo para el navegador automático)",
            ayuda="Dejala vacía para conservar la clave actual."
            if self._tiene_clave
            else "La misma que usás para entrar a la web de ARCA.",
            show="•",
        )

        ttk.Label(marco, text="Carpeta donde guardar las facturas").grid(
            row=9, column=0, columnspan=2, sticky="w"
        )
        self.carpeta = ttk.StringVar(
            value=os.getenv("DOWNLOAD_PATH") or str(DEFAULT_DOWNLOAD_PATH)
        )
        ttk.Entry(marco, textvariable=self.carpeta).grid(
            row=10, column=0, sticky="ew", pady=(4, 0)
        )
        ttk.Button(
            marco,
            text="Examinar…",
            bootstyle="secondary-outline",
            command=self._elegir_carpeta,
        ).grid(row=10, column=1, padx=(8, 0), pady=(4, 0))

    def _crear_api(self):
        marco = self._pestana("API de ARCA")
        marco.columnconfigure((0, 1), weight=1, uniform="columna")

        self.condicion = self._lista(
            marco, 0, 0, "Tu condición fiscal", CONDICIONES_EMISOR.values(),
            CONDICIONES_EMISOR.get(
                os.getenv("ARCA_CONDICION"), CONDICIONES_EMISOR["monotributo"]
            ),
        )
        self.ambiente = self._lista(
            marco, 0, 1, "Ambiente", AMBIENTES.values(),
            AMBIENTES.get(os.getenv("ARCA_AMBIENTE"), AMBIENTES["produccion"]),
        )

        ttk.Label(marco, text="Punto de venta (web services)").grid(
            row=2, column=0, sticky="w"
        )
        self.punto_venta = ttk.Entry(marco, width=10)
        self.punto_venta.insert(0, os.getenv("ARCA_PTO_VTA", ""))
        self.punto_venta.grid(row=3, column=0, sticky="ew", pady=(4, 12))
        self.alicuota = self._lista(
            marco, 2, 1, "IVA % (solo Responsable Inscripto)", ALICUOTAS,
            os.getenv("ARCA_ALICUOTA", "21"),
        )

        archivos = ttk.Frame(marco)
        archivos.grid(row=4, column=0, columnspan=2, sticky="ew")
        archivos.columnconfigure(0, weight=1)
        self.certificado = self._archivo(
            archivos, 0, "Certificado (.crt) descargado de ARCA",
            os.getenv("ARCA_CERT", ""),
            [("Certificados", "*.crt *.pem *.cer"), ("Todos", "*.*")],
        )
        self.clave_privada = self._archivo(
            archivos, 2, "Clave privada (.key)", os.getenv("ARCA_PRIVATE_KEY", ""),
            [("Claves", "*.key *.pem"), ("Todos", "*.*")],
        )

        ttk.Button(
            marco,
            text="No tengo certificado: generar clave y pedido…",
            bootstyle="primary-link",
            command=self._generar_certificado,
        ).grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Label(
            marco,
            text="Los precios que cargás se toman como finales (IVA incluido).",
            bootstyle="secondary",
            font=FUENTE_AYUDA,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _crear_emisor(self):
        marco = self._pestana("Datos del emisor")
        ttk.Label(
            marco,
            text="Aparecen en el PDF de las facturas emitidas por la API.",
            bootstyle="secondary",
            font=FUENTE_AYUDA,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self.emisor = {
            "EMISOR_NOMBRE": self._campo(
                marco, 1, "Nombre o razón social", os.getenv("EMISOR_NOMBRE", "")
            ),
            "EMISOR_DOMICILIO": self._campo(
                marco, 3, "Domicilio comercial", os.getenv("EMISOR_DOMICILIO", "")
            ),
            "EMISOR_IIBB": self._campo(
                marco, 5, "Ingresos Brutos", os.getenv("EMISOR_IIBB", "")
            ),
            "EMISOR_INICIO": self._campo(
                marco, 7, "Inicio de actividades (dd/mm/aaaa)",
                os.getenv("EMISOR_INICIO", ""),
            ),
        }

    # ------------------------------------------------------------ Acciones

    def _elegir_carpeta(self):
        carpeta = filedialog.askdirectory(
            parent=self, title="Carpeta donde guardar las facturas"
        )
        if carpeta:
            self.carpeta.set(carpeta)

    def _error(self, pestana, titulo, mensaje):
        self.pestanas.select(pestana)
        messagebox.showerror(titulo, mensaje, parent=self)

    def _generar_certificado(self):
        cuit = solo_digitos(self.cuil.get())
        if not cuit_valido(cuit):
            self._error(0, "Falta el CUIT", "Primero cargá un CUIT válido en «General».")
            return
        # Se importa acá para no cargar la criptografía si no se usa.
        from services.certificado import (  # pylint: disable=import-outside-toplevel
            generar_clave_y_pedido,
        )

        try:
            ruta_clave, _ = generar_clave_y_pedido(
                cuit, self.emisor["EMISOR_NOMBRE"].get().strip() or "MiFactura"
            )
        except OSError as error:
            messagebox.showerror(
                "No se pudo generar", f"Error al crear los archivos:\n{error}", parent=self
            )
            return
        self.clave_privada.set(ruta_clave.as_posix())
        messagebox.showinfo(
            "Pedido de certificado generado",
            PASOS_CERTIFICADO.format(carpeta=ruta_clave.parent),
            parent=self,
        )
        try:
            os.startfile(ruta_clave.parent)  # pylint: disable=no-member
        except (AttributeError, OSError):
            pass

    def _guardar(self):
        # pylint: disable=too-many-return-statements
        motor = self.motor.get()
        cuil = solo_digitos(self.cuil.get())
        clave = self.clave.get().strip()
        carpeta = self.carpeta.get().strip()
        punto_venta = self.punto_venta.get().strip()
        certificado = self.certificado.get().strip()
        clave_privada = self.clave_privada.get().strip()

        if not cuit_valido(cuil):
            self._error(0, "Dato inválido", "El CUIT no es válido.")
            return
        if not carpeta:
            self._error(0, "Falta la carpeta", "Elegí una carpeta de descarga.")
            return
        if motor == "web" and not clave and not self._tiene_clave:
            self._error(0, "Falta la clave", "Ingresá tu clave fiscal.")
            return
        if motor == "api":
            if not punto_venta.isdigit() or int(punto_venta) < 1:
                self._error(1, "Falta el punto de venta", "Ingresá el número de punto de venta.")
                return
            if not os.path.isfile(certificado):
                self._error(1, "Falta el certificado", "Elegí el archivo .crt descargado de ARCA.")
                return
            if not os.path.isfile(clave_privada):
                self._error(1, "Falta la clave privada", "Elegí el archivo .key.")
                return
            if not self.emisor["EMISOR_NOMBRE"].get().strip():
                self._error(2, "Falta el emisor", "Ingresá tu nombre o razón social.")
                return

        valores = {
            "ARCA_MOTOR": motor,
            "ARCA_CUIL": cuil,
            "ARCA_KEY": clave or None,
            "DOWNLOAD_PATH": carpeta.replace("\\", "/"),
            "ARCA_CONDICION": _clave_de(CONDICIONES_EMISOR, self.condicion.get()),
            "ARCA_AMBIENTE": _clave_de(AMBIENTES, self.ambiente.get()),
            "ARCA_PTO_VTA": punto_venta,
            "ARCA_ALICUOTA": self.alicuota.get(),
            "ARCA_CERT": certificado.replace("\\", "/"),
            "ARCA_PRIVATE_KEY": clave_privada.replace("\\", "/"),
        }
        valores.update({k: campo.get().strip() for k, campo in self.emisor.items()})
        try:
            os.makedirs(carpeta, exist_ok=True)
            save_settings(valores)
        except OSError as error:
            messagebox.showerror(
                "No se pudo guardar", f"Error al guardar:\n{error}", parent=self
            )
            return
        self.guardado = True
        self.destroy()


class HistoryDialog(ttk.Toplevel):
    """Listado de facturas emitidas, con exportación a Excel."""

    COLUMNAS = (
        ("numero", "N°", 60, "center"),
        ("fecha", "Fecha", 140, "w"),
        ("cliente", "Cliente", 130, "w"),
        ("condicion", "Condición IVA", 190, "w"),
        ("items", "Ítems", 60, "center"),
        ("total", "Total", 130, "e"),
    )

    def __init__(self, parent):
        super().__init__(parent)
        _preparar(self, parent, "Historial · MiFactura")
        self.minsize(760, 420)

        cuerpo = ttk.Frame(self, padding=20)
        cuerpo.pack(fill="both", expand=True)
        cuerpo.columnconfigure(0, weight=1)
        cuerpo.rowconfigure(1, weight=1)

        facturas = listar_facturas()
        total = sum(f.valor_total or 0 for f in facturas)

        encabezado = ttk.Frame(cuerpo)
        encabezado.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        ttk.Label(encabezado, text="Facturas emitidas", font=FUENTE_TITULO).pack(
            side="left"
        )
        ttk.Label(
            encabezado,
            text=f"{len(facturas)} facturas · {formatear_pesos(total)}",
            bootstyle="secondary",
        ).pack(side="left", padx=12, pady=(5, 0))
        self.boton_exportar = ttk.Button(
            encabezado,
            text="Exportar a Excel",
            bootstyle="success-outline",
            command=self._exportar,
        )
        self.boton_exportar.pack(side="right")
        if not facturas:
            self.boton_exportar.configure(state="disabled")

        tabla = ttk.Treeview(
            cuerpo,
            columns=[c[0] for c in self.COLUMNAS],
            show="headings",
            selectmode="browse",
        )
        for clave, titulo, ancho, alineacion in self.COLUMNAS:
            tabla.heading(clave, text=titulo, anchor=alineacion)
            tabla.column(clave, width=ancho, anchor=alineacion)
        barra = ttk.Scrollbar(cuerpo, orient="vertical", command=tabla.yview)
        tabla.configure(yscrollcommand=barra.set)
        tabla.grid(row=1, column=0, sticky="nsew")
        barra.grid(row=1, column=1, sticky="ns")

        for factura in facturas:
            productos = factura.productos if isinstance(factura.productos, list) else []
            condicion = factura.condicion_iva_rel
            tabla.insert(
                "",
                "end",
                values=(
                    factura.id,
                    factura.fecha.strftime("%d/%m/%Y %H:%M") if factura.fecha else "",
                    factura.id_cliente or "—",
                    condicion.nombre_de_condicion if condicion else "",
                    len(productos),
                    formatear_pesos(factura.valor_total or 0),
                ),
            )

        if not facturas:
            ttk.Label(
                cuerpo, text="Todavía no emitiste ninguna factura.", bootstyle="secondary"
            ).grid(row=2, column=0, pady=(12, 0))

        self.bind("<Escape>", lambda _e: self.destroy())
        _centrar(self)
        self.grab_set()

    def _exportar(self):
        ruta = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".xlsx",
            initialfile="Historial de facturas.xlsx",
            filetypes=[("Archivos Excel", "*.xlsx")],
            title="Guardar historial como…",
        )
        if not ruta:
            return
        try:
            cantidad = exportar_historial(ruta)
        except OSError as error:
            messagebox.showerror(
                "No se pudo exportar",
                f"No se pudo guardar el archivo (¿está abierto en Excel?).\n\n{error}",
                parent=self,
            )
            return
        messagebox.showinfo(
            "Historial exportado",
            f"Se exportaron {cantidad} facturas a:\n{ruta}",
            parent=self,
        )
