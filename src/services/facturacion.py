"""Punto único de emisión: elige el motor configurado (API o navegador)."""

import os

from services.comun import FacturacionError

__all__ = ["FacturacionError", "emitir_factura", "motor", "descripcion_comprobante"]


def motor():
    """Motor de facturación configurado: "api" o "web"."""
    return "api" if os.getenv("ARCA_MOTOR") == "api" else "web"


def descripcion_comprobante(condicion_receptor):
    """Texto del comprobante que se va a emitir, para mostrar antes de confirmar."""
    if motor() != "api":
        return "Factura (Comprobantes en línea)"
    from services import wsfe  # pylint: disable=import-outside-toplevel

    letra = wsfe.letra_comprobante(
        os.getenv("ARCA_CONDICION", "monotributo"), condicion_receptor
    )
    ambiente = (
        " · HOMOLOGACIÓN (sin validez fiscal)"
        if os.getenv("ARCA_AMBIENTE") == "homologacion"
        else ""
    )
    return f"Factura {letra}{ambiente}"


def emitir_factura(tipo_documento, client_id, condicion_iva, products, on_progress=None):
    """Emite la factura con el motor configurado.

    Returns:
        dict: {"emitida": bool, "pdf": Path | None, "carpeta": Path, "detalle"?: str}
    """
    # Cada motor se importa al usarlo: así no se cargan Selenium ni la
    # criptografía si no hacen falta.
    # pylint: disable=import-outside-toplevel
    if motor() == "api":
        from services import wsfe as implementacion
    else:
        from services import afip_client as implementacion
    return implementacion.emitir_factura(
        tipo_documento, client_id, condicion_iva, products, on_progress
    )
