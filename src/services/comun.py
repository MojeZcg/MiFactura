"""Piezas compartidas por los motores de facturación."""

import os
from datetime import datetime
from pathlib import Path

MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip

NO_EMITIDA = "La factura NO fue emitida."
SIN_VERIFICAR = (
    "No se pudo verificar si la factura llegó a emitirse: revisá en ARCA "
    "antes de volver a intentarlo."
)


class FacturacionError(Exception):
    """Fallo durante la emisión, con un mensaje apto para mostrar al usuario."""


def carpeta_de_descarga():
    """Carpeta del día dentro de DOWNLOAD_PATH (se crea si no existe)."""
    base = os.getenv("DOWNLOAD_PATH")
    if not base:
        raise FacturacionError(
            "No hay carpeta de descarga configurada. Revisá Configuración."
        )
    hoy = datetime.now()
    carpeta = Path(base) / f"{hoy.day:02d} de {MESES[hoy.month - 1]} {hoy.year}"
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise FacturacionError(
            f"No se pudo crear la carpeta de descarga:\n{carpeta}\n{error}"
        ) from error
    return carpeta
