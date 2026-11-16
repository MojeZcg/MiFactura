"""Genera el PDF de una factura emitida por la API (ARCA solo entrega el CAE)."""

import os
from datetime import datetime
from decimal import Decimal

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from utils.formato import formatear_cuit, formatear_pesos, numero_a_texto

GRIS = colors.HexColor("#6c757d")
BORDE = colors.HexColor("#adb5bd")
ANCHO = A4[0] - 30 * mm

NORMAL = ParagraphStyle("normal", fontName="Helvetica", fontSize=9, leading=12)
CHICO = ParagraphStyle("chico", parent=NORMAL, fontSize=8, textColor=GRIS)
NOMBRE = ParagraphStyle("nombre", parent=NORMAL, fontName="Helvetica-Bold", fontSize=14, leading=18)
TITULO = ParagraphStyle("titulo", parent=NORMAL, fontName="Helvetica-Bold", fontSize=16, leading=20)
LETRA = ParagraphStyle("letra", parent=NORMAL, fontName="Helvetica-Bold", fontSize=30, leading=32, alignment=1)
CENTRADO = ParagraphStyle("centrado", parent=CHICO, alignment=1)
DERECHA = ParagraphStyle("derecha", parent=NORMAL, alignment=2)
DERECHA_NEGRITA = ParagraphStyle("derecha_negrita", parent=DERECHA, fontName="Helvetica-Bold", fontSize=11)


def _texto(valor):
    return str(valor).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fecha_cae(valor):
    try:
        return datetime.strptime(valor, "%Y%m%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return valor or ""


def _qr(url, lado=34 * mm):
    widget = QrCodeWidget(url)
    x0, y0, x1, y1 = widget.getBounds()
    dibujo = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0, lado / (y1 - y0), 0, 0])
    dibujo.add(widget)
    return dibujo


def _encabezado(datos):
    emisor = [
        Paragraph(_texto(os.getenv("EMISOR_NOMBRE", "")), NOMBRE),
        Spacer(1, 4),
        Paragraph(_texto(os.getenv("EMISOR_DOMICILIO", "")), NORMAL),
        Paragraph(f"Condición frente al IVA: <b>{datos['condicion_emisor']}</b>", NORMAL),
    ]
    letra = [
        Paragraph(datos["letra"], LETRA),
        Paragraph(f"COD. {datos['codigo']:03d}", CENTRADO),
    ]
    comprobante = [
        Paragraph("FACTURA", TITULO),
        Paragraph(
            f"Punto de Venta: <b>{datos['punto_venta']:05d}</b> &nbsp; "
            f"Comp. Nro: <b>{datos['numero']:08d}</b>",
            NORMAL,
        ),
        Paragraph(f"Fecha de emisión: <b>{datos['fecha']:%d/%m/%Y}</b>", NORMAL),
        Paragraph(f"CUIT: {formatear_cuit(datos['cuit'])}", NORMAL),
        Paragraph(f"Ingresos Brutos: {_texto(os.getenv('EMISOR_IIBB', ''))}", NORMAL),
        Paragraph(
            f"Inicio de actividades: {_texto(os.getenv('EMISOR_INICIO', ''))}", NORMAL
        ),
    ]
    tabla = Table([[emisor, letra, comprobante]], colWidths=[ANCHO * 0.44, ANCHO * 0.12, ANCHO * 0.44])
    tabla.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.8, BORDE),
                ("BOX", (1, 0), (1, 0), 0.8, BORDE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return tabla


def _receptor(datos):
    if datos["documento"]:
        numero = datos["documento"]
        if datos["tipo_documento"] != "DNI":
            numero = formatear_cuit(numero)
        documento = f"{datos['tipo_documento']}: <b>{numero}</b>"
    else:
        documento = "Cliente: <b>Consumidor final</b>"
    tabla = Table(
        [
            [
                Paragraph(documento, NORMAL),
                Paragraph(
                    f"Condición frente al IVA: <b>{datos['condicion_receptor']}</b>",
                    NORMAL,
                ),
                Paragraph("Condición de venta: <b>Contado</b>", NORMAL),
            ]
        ],
        colWidths=[ANCHO * 0.3, ANCHO * 0.42, ANCHO * 0.28],
    )
    tabla.setStyle(
        TableStyle(
            [("BOX", (0, 0), (-1, -1), 0.8, BORDE), ("TOPPADDING", (0, 0), (-1, -1), 7),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 8)]
        )
    )
    return tabla


def _detalle(datos):
    # En la Factura A los precios se muestran sin IVA; en B y C, finales.
    divisor = Decimal(1)
    if datos["letra"] == "A":
        divisor = 1 + Decimal(datos["alicuota"]) / 100
    filas = [["Descripción", "Cantidad", "Precio unit.", "Subtotal"]]
    for descripcion, cantidad, precio, subtotal in datos["lineas"]:
        filas.append(
            [
                Paragraph(_texto(descripcion), NORMAL),
                numero_a_texto(cantidad),
                formatear_pesos(precio / divisor),
                formatear_pesos(subtotal / divisor),
            ]
        )
    tabla = Table(
        filas,
        colWidths=[ANCHO * 0.52, ANCHO * 0.12, ANCHO * 0.18, ANCHO * 0.18],
        repeatRows=1,
    )
    tabla.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9ecef")),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, BORDE),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return tabla


def _totales(datos):
    filas = []
    if datos["letra"] == "A":
        filas.append(["Importe neto gravado", formatear_pesos(datos["neto"])])
        filas.append([f"IVA {datos['alicuota']}%", formatear_pesos(datos["iva"])])
    filas.append(
        [
            Paragraph("<b>Importe total</b>", DERECHA_NEGRITA),
            Paragraph(formatear_pesos(datos["total"]), DERECHA_NEGRITA),
        ]
    )
    tabla = Table(filas, colWidths=[ANCHO * 0.78, ANCHO * 0.22])
    tabla.setStyle(
        TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 9)])
    )
    return tabla


def _pie(datos):
    textos = [
        Paragraph(f"CAE N°: <b>{datos['cae']}</b>", DERECHA),
        Paragraph(
            f"Fecha de Vto. de CAE: <b>{_fecha_cae(datos['cae_vencimiento'])}</b>",
            DERECHA,
        ),
        Spacer(1, 6),
        Paragraph("Comprobante autorizado por ARCA", ParagraphStyle("pie", parent=CHICO, alignment=2)),
    ]
    tabla = Table([[_qr(datos["qr"]), textos]], colWidths=[40 * mm, ANCHO - 40 * mm])
    tabla.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return tabla


def generar_pdf(ruta, datos):
    """Escribe el PDF de la factura en `ruta` y devuelve esa ruta."""
    contenido = [
        _encabezado(datos),
        Spacer(1, 8),
        _receptor(datos),
        Spacer(1, 12),
        _detalle(datos),
        Spacer(1, 10),
        _totales(datos),
    ]
    if datos["letra"] == "B":
        contenido += [
            Spacer(1, 6),
            Paragraph(
                "Régimen de Transparencia Fiscal al Consumidor (Ley 27.743) · "
                f"IVA contenido: {formatear_pesos(datos['iva'])}",
                ParagraphStyle("transparencia", parent=CHICO, alignment=2),
            ),
        ]
    contenido += [Spacer(1, 18), _pie(datos)]

    documento = SimpleDocTemplate(
        str(ruta),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Factura {datos['letra']} {datos['punto_venta']:05d}-{datos['numero']:08d}",
        author=os.getenv("EMISOR_NOMBRE", ""),
    )
    documento.build(contenido)
    return ruta
