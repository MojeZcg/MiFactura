import os
import ttkbootstrap as ttk
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from models.database import Facturas
from models.database import Session
from utils.helpers import center_window




class History:
    """
    Clase que muestra el historial de facturas

    Attributes:
        root (tk.Tk): La ventana principal de la aplicación.
        icon_path (str): La ruta del icono de la ventana de progreso.
        progress_window (tk.Toplevel): La ventana de progreso.
        progress_bar (ttk.Progressbar): La barra de progreso.
    """
    def __init__(self, r):
        """
        Inicializa una instancia de History.

        Args:
            root (tk.Tk): La ventana principal de la aplicación.
            text (str): El texto que se mostrará en la ventana de progreso.
        """
        self.root = r
        self.icon_path = os.getenv("ICON_PATH")
        self.create_history_window()
        center_window(self.root)

    def create_history_window(self):
        """
        Crea y configura la ventana de progreso y la barra de progreso.

        Args:
            text (str): El texto que se mostrará en la ventana de progreso.
        """
        self.h = ttk.Toplevel(self.root)
        self.h.geometry("600x400")
        self.h.title("Historial")
        self.h.iconbitmap(self.icon_path)

        self.history_tree = ttk.Treeview(
            self.h,
            bootstyle="dark",
            columns=(
                "id",
                "document_type",
                "iva_condition",
                "total_value",
                "time_billing"
            ),
            show='headings'
        )
        self.history_tree.heading("id", text="Numero de Doc.")
        self.history_tree.heading("document_type", text="Tipo")
        self.history_tree.heading("iva_condition", text="Condición Iva")
        self.history_tree.heading("total_value", text="Valor Total")
        self.history_tree.heading("time_billing", text="Fecha de Facturación")

        self.history_tree.column("id", anchor=ttk.CENTER, width=90)
        self.history_tree.column("document_type",anchor=ttk.CENTER,  width=50)
        self.history_tree.column("iva_condition", anchor=ttk.CENTER, width=100)
        self.history_tree.column("total_value", anchor=ttk.CENTER, width=100)
        self.history_tree.column("time_billing", anchor=ttk.CENTER, width=100)
        self.history_tree.place(x=5, y=5, width=590,height=350)

        self.exit_button = ttk.Button(
            self.h,
            bootstyle="danger-outline",
            text="Cerrar historial",
            command=self.close_history_window
        )
        self.exit_button.place(x=455, y=365, width=140, height=28)

        self.load_data()

    def load_data(self):
        """Función para cargar datos al Treeview"""
        with Session() as sess:
            # Realizar la consulta usando joinedload para evitar NoneType
            stmt = select(Facturas).options(
                joinedload(Facturas.tipo_de_documento),
                joinedload(Facturas.condicion_iva_rel)
            )
            result = sess.execute(stmt)
            bills = result.scalars().all()

            # Insertar los datos en el Treeview
            for bill in bills:
                formated_date = bill.fecha.strftime('%d-%m-%Y') if bill.fecha else 'N/A'
                print( f'Tipo: {bill.tipo_de_documento}')
                tipo_de_documento_nombre = bill.tipo_de_documento.nombre_de_tipo if bill.tipo_de_documento else 'Desconocido' # pylint: disable=line-too-long
                condicion_iva_nombre = bill.condicion_iva_rel.nombre_de_condicion if bill.condicion_iva_rel else 'Desconocido' # pylint: disable=line-too-long

                self.history_tree.insert('', ttk.END, values=(
                    bill.id_cliente,
                    tipo_de_documento_nombre,
                    condicion_iva_nombre,
                    f'{bill.valor_total}$' if bill.valor_total else '0$',
                    formated_date
                ))
            self.history_tree.update()

    def close_history_window(self):
        """
        Cerrar el historial
        """
        self.h.destroy()
