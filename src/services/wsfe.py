"""Emisión de facturas por la API oficial de ARCA (web service WSFEv1).

No usa navegador: pide el CAE directamente a ARCA y genera el PDF localmente.
Requiere un certificado digital y un punto de venta habilitado para web services.
"""

import base64
import json
import logging
import os
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from config import is_debug
from services import wsaa
from services.comun import (
    NO_EMITIDA,
    SIN_VERIFICAR,
    FacturacionError,
    carpeta_de_descarga,
)

logger = logging.getLogger(__name__)

NAMESPACE = "http://ar.gov.afip.dif.FEV1/"
URLS = {
    "produccion": "https://servicios1.afip.gov.ar/wsfev1/service.asmx",
    "homologacion": "https://wswhomo.afip.gov.ar/wsfev1/service.asmx",
}

CODIGO_COMPROBANTE = {"A": 1, "B": 6, "C": 11}
CODIGO_DOCUMENTO = {"CUIT": 80, "CUIL": 86, "DNI": 96}
DOCUMENTO_SIN_IDENTIFICAR = 99
CONDICION_IVA_RECEPTOR = {
    "Consumidor Final": 5,
    "Iva Responsable Inscripto": 1,
    "Iva Sujeto Exento": 4,
}
CODIGO_ALICUOTA = {"21": 5, "10.5": 4, "27": 6}
CONCEPTO_PRODUCTOS = 1
CENTAVO = Decimal("0.01")

CONDICIONES_EMISOR = {
    "monotributo": "Responsable Monotributo",
    "ri": "IVA Responsable Inscripto",
}


def _redondear(valor):
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def letra_comprobante(condicion_emisor, condicion_receptor):
    """Monotributo emite C; un responsable inscripto, A a otro RI y B al resto."""
    if condicion_emisor == "monotributo":
        return "C"
    return "A" if condicion_receptor == "Iva Responsable Inscripto" else "B"


def calcular_importes(products, letra, alicuota):
    """Totales de la factura. Los precios cargados son finales (IVA incluido)."""
    lineas = []
    for product in products:
        cantidad = Decimal(product["Quantity"])
        precio = Decimal(product["Price"])
        lineas.append(
            (product["Product"], cantidad, precio, _redondear(cantidad * precio))
        )
    total = sum((linea[3] for linea in lineas), Decimal("0"))
    if letra == "C":
        neto, iva = total, Decimal("0")
    else:
        neto = _redondear(total / (1 + Decimal(alicuota) / 100))
        iva = total - neto
    return {"lineas": lineas, "total": total, "neto": neto, "iva": iva}


def leer_configuracion():
    """Lee y valida la configuración de la API desde el entorno."""
    cuit = os.getenv("ARCA_CUIL", "")
    certificado = os.getenv("ARCA_CERT", "")
    clave = os.getenv("ARCA_PRIVATE_KEY", "")
    punto_venta = os.getenv("ARCA_PTO_VTA", "")
    condicion = os.getenv("ARCA_CONDICION", "monotributo")
    ambiente = os.getenv("ARCA_AMBIENTE", "produccion")
    alicuota = os.getenv("ARCA_ALICUOTA", "21")

    faltan = []
    if not cuit.isdigit():
        faltan.append("el CUIT")
    if not punto_venta.isdigit() or int(punto_venta) < 1:
        faltan.append("el punto de venta")
    if not certificado or not Path(certificado).is_file():
        faltan.append("el certificado (.crt)")
    if not clave or not Path(clave).is_file():
        faltan.append("la clave privada (.key)")
    if faltan:
        raise FacturacionError(
            "Falta configurar " + ", ".join(faltan) + " para usar la API de ARCA."
        )
    if condicion not in CONDICIONES_EMISOR or ambiente not in URLS:
        raise FacturacionError("La configuración de la API de ARCA no es válida.")
    if alicuota not in CODIGO_ALICUOTA:
        raise FacturacionError(f"Alícuota de IVA no soportada: {alicuota}%.")
    return {
        "cuit": cuit,
        "certificado": certificado,
        "clave": clave,
        "punto_venta": int(punto_venta),
        "condicion": condicion,
        "ambiente": ambiente,
        "alicuota": alicuota,
    }


def _a_xml(datos):
    """Convierte dicts anidados en elementos XML, respetando el orden."""
    partes = []
    for nombre, valor in datos.items():
        contenido = _a_xml(valor) if isinstance(valor, dict) else escape(str(valor))
        partes.append(f"<{nombre}>{contenido}</{nombre}>")
    return "".join(partes)


def _llamar(config, ticket, operacion, parametros):
    cuerpo = _a_xml(
        {
            "Auth": {
                "Token": ticket["token"],
                "Sign": ticket["sign"],
                "Cuit": config["cuit"],
            },
            **parametros,
        }
    )
    respuesta = wsaa.enviar_soap(
        URLS[config["ambiente"]],
        f'<{operacion} xmlns="{NAMESPACE}">{cuerpo}</{operacion}>',
        NAMESPACE + operacion,
    )
    resultado = respuesta.find(f".//{operacion}Result")
    if resultado is None:
        raise FacturacionError("ARCA devolvió una respuesta inesperada.")
    return resultado


def _mensajes(resultado, ruta):
    return [
        f"{item.findtext('Code')}: {item.findtext('Msg')}"
        for item in resultado.findall(ruta)
    ]


def ultimo_comprobante(config, ticket, codigo):
    """Número del último comprobante autorizado para el punto de venta y tipo."""
    resultado = _llamar(
        config,
        ticket,
        "FECompUltimoAutorizado",
        {"PtoVta": config["punto_venta"], "CbteTipo": codigo},
    )
    errores = _mensajes(resultado, "Errors/Err")
    if errores:
        raise FacturacionError(
            "ARCA rechazó la consulta de numeración:\n" + "\n".join(errores)
        )
    return int(resultado.findtext("CbteNro"))


def armar_detalle(numero, fecha, letra, importes, doc_tipo, doc_nro, receptor, alicuota):
    """Detalle del comprobante en el orden que exige el WSDL de WSFEv1."""
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    detalle = {
        "Concepto": CONCEPTO_PRODUCTOS,
        "DocTipo": doc_tipo,
        "DocNro": doc_nro,
        "CbteDesde": numero,
        "CbteHasta": numero,
        "CbteFch": fecha.strftime("%Y%m%d"),
        "ImpTotal": f"{importes['total']:.2f}",
        "ImpTotConc": "0.00",
        "ImpNeto": f"{importes['neto']:.2f}",
        "ImpOpEx": "0.00",
        "ImpTrib": "0.00",
        "ImpIVA": f"{importes['iva']:.2f}",
        "MonId": "PES",
        "MonCotiz": "1",
        "CondicionIVAReceptorId": CONDICION_IVA_RECEPTOR[receptor],
    }
    if letra != "C":
        detalle["Iva"] = {
            "AlicIva": {
                "Id": CODIGO_ALICUOTA[alicuota],
                "BaseImp": f"{importes['neto']:.2f}",
                "Importe": f"{importes['iva']:.2f}",
            }
        }
    return detalle


def interpretar_cae(resultado):
    """Devuelve (cae, vencimiento) o lanza FacturacionError con el motivo."""
    detalle = resultado.find("FeDetResp/FECAEDetResponse")
    cae = detalle.findtext("CAE") if detalle is not None else None
    if detalle is not None and detalle.findtext("Resultado") == "A" and cae:
        return cae, detalle.findtext("CAEFchVto")
    motivos = _mensajes(resultado, "Errors/Err")
    if detalle is not None:
        motivos += _mensajes(detalle, "Observaciones/Obs")
    raise FacturacionError(
        "ARCA rechazó la factura:\n"
        + ("\n".join(motivos) or "sin detalle")
        + f"\n\n{NO_EMITIDA}"
    )


def url_qr(config, codigo, numero, fecha, total, doc_tipo, doc_nro, cae):
    """URL del código QR obligatorio del comprobante (RG 4892)."""
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    datos = {
        "ver": 1,
        "fecha": fecha.strftime("%Y-%m-%d"),
        "cuit": int(config["cuit"]),
        "ptoVta": config["punto_venta"],
        "tipoCmp": codigo,
        "nroCmp": numero,
        "importe": float(total),
        "moneda": "PES",
        "ctz": 1,
        "tipoDocRec": doc_tipo,
        "nroDocRec": int(doc_nro),
        "tipoCodAut": "E",
        "codAut": int(cae),
    }
    codificado = base64.b64encode(json.dumps(datos).encode("utf-8")).decode("ascii")
    return "https://www.afip.gob.ar/fe/qr/?p=" + codificado


def emitir_factura(tipo_documento, client_id, condicion_iva, products, on_progress=None):
    """Emite una factura por la API. Misma interfaz que el motor por navegador."""
    # pylint: disable=too-many-locals
    etapa = "Preparando"
    solicitud_enviada = False

    def paso(porcentaje, mensaje):
        nonlocal etapa
        etapa = mensaje
        logger.info("%s%% %s", porcentaje, mensaje)
        if on_progress:
            on_progress(porcentaje, mensaje)

    config = leer_configuracion()
    carpeta = carpeta_de_descarga()
    letra = letra_comprobante(config["condicion"], condicion_iva)
    codigo = CODIGO_COMPROBANTE[letra]
    importes = calcular_importes(products, letra, config["alicuota"])
    if client_id:
        doc_tipo, doc_nro = CODIGO_DOCUMENTO[tipo_documento], client_id
    else:
        doc_tipo, doc_nro = DOCUMENTO_SIN_IDENTIFICAR, "0"
    fecha = datetime.now()
    resultado = {"emitida": False, "pdf": None, "carpeta": carpeta}

    try:
        paso(15, "Autenticando con ARCA")
        ticket = wsaa.obtener_ticket(
            config["ambiente"], config["cuit"], config["certificado"], config["clave"]
        )

        paso(40, "Consultando la numeración")
        numero = ultimo_comprobante(config, ticket, codigo) + 1

        if is_debug():
            paso(100, "Simulación terminada (modo DEBUG: no se pidió el CAE)")
            return resultado

        paso(60, f"Solicitando el CAE de la Factura {letra}")
        solicitud_enviada = True
        respuesta = _llamar(
            config,
            ticket,
            "FECAESolicitar",
            {
                "FeCAEReq": {
                    "FeCabReq": {
                        "CantReg": 1,
                        "PtoVta": config["punto_venta"],
                        "CbteTipo": codigo,
                    },
                    "FeDetReq": {
                        "FECAEDetRequest": armar_detalle(
                            numero, fecha, letra, importes, doc_tipo, doc_nro,
                            condicion_iva, config["alicuota"],
                        )
                    },
                }
            },
        )
        cae, vencimiento = interpretar_cae(respuesta)
    except FacturacionError:
        raise
    except (urllib.error.URLError, OSError, ET.ParseError, ValueError) as error:
        logger.exception("Fallo de comunicación con ARCA en: %s", etapa)
        raise FacturacionError(
            f"No se pudo comunicar con ARCA en el paso «{etapa}».\n"
            f"{SIN_VERIFICAR if solicitud_enviada else NO_EMITIDA}\n\n{error}"
        ) from error

    resultado["emitida"] = True
    identificador = f"Factura {letra} {config['punto_venta']:05d}-{numero:08d}"
    resultado["detalle"] = f"{identificador} · CAE {cae}"
    logger.info("Emitida %s", resultado["detalle"])

    paso(85, "Generando el PDF")
    try:
        from services.pdf import generar_pdf  # pylint: disable=import-outside-toplevel

        resultado["pdf"] = generar_pdf(
            carpeta / f"{identificador}.pdf",
            {
                "letra": letra,
                "codigo": codigo,
                "punto_venta": config["punto_venta"],
                "numero": numero,
                "fecha": fecha,
                "cuit": config["cuit"],
                "condicion_emisor": CONDICIONES_EMISOR[config["condicion"]],
                "tipo_documento": tipo_documento if client_id else "",
                "documento": client_id,
                "condicion_receptor": condicion_iva,
                "alicuota": config["alicuota"],
                "cae": cae,
                "cae_vencimiento": vencimiento,
                "qr": url_qr(
                    config, codigo, numero, fecha, importes["total"],
                    doc_tipo, doc_nro, cae,
                ),
                **importes,
            },
        )
    except Exception:  # pylint: disable=broad-except
        logger.exception("La factura se emitió pero no se pudo generar el PDF")

    paso(100, "Factura emitida")
    return resultado
