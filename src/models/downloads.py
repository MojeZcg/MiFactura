"""Exportación del historial de facturas a Excel."""

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from models.database import listar_facturas

COLUMNAS = (
    ("Factura N°", 11),
    ("Fecha", 19),
    ("Cliente", 16),
    ("Condición IVA", 26),
    ("Producto", 34),
    ("Cantidad", 11),
    ("Precio unitario", 16),
    ("Subtotal", 16),
    ("Total factura", 16),
)
FORMATO_PESOS = '"$" #,##0.00'


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def exportar_historial(ruta):
    """Escribe el historial en `ruta` (.xlsx). Devuelve la cantidad de facturas."""
    facturas = listar_facturas()

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Historial"
    hoja.append([titulo for titulo, _ in COLUMNAS])
    for indice, (_, ancho) in enumerate(COLUMNAS, start=1):
        celda = hoja.cell(row=1, column=indice)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="0D6EFD")
        celda.alignment = Alignment(horizontal="center")
        hoja.column_dimensions[get_column_letter(indice)].width = ancho
    hoja.freeze_panes = "A2"

    for factura in facturas:
        productos = factura.productos if isinstance(factura.productos, list) else []
        condicion = factura.condicion_iva_rel
        comunes = [
            factura.id,
            factura.fecha.strftime("%d/%m/%Y %H:%M") if factura.fecha else "",
            factura.id_cliente or "—",
            condicion.nombre_de_condicion if condicion else "",
        ]
        if not productos:
            hoja.append(comunes + ["(sin detalle)", None, None, None, factura.valor_total])
            continue
        for producto in productos:
            cantidad = _numero(producto.get("Quantity"))
            precio = _numero(producto.get("Price"))
            subtotal = cantidad * precio if None not in (cantidad, precio) else None
            hoja.append(
                comunes
                + [producto.get("Product", ""), cantidad, precio, subtotal, factura.valor_total]
            )

    for fila in hoja.iter_rows(min_row=2, min_col=7, max_col=9):
        for celda in fila:
            celda.number_format = FORMATO_PESOS

    libro.save(ruta)
    return len(facturas)
