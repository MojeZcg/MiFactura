"""Autenticación contra ARCA (WSAA) con certificado digital.

Devuelve el ticket de acceso (token + sign) que piden los demás web services.
El ticket dura unas 12 horas y ARCA no entrega otro mientras siga vigente,
por eso se guarda en disco.
"""

import base64
import json
import logging
import ssl
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from config import APP_DIR
from services.comun import FacturacionError

logger = logging.getLogger(__name__)

URLS = {
    "produccion": "https://wsaa.afip.gov.ar/ws/services/LoginCms",
    "homologacion": "https://wsaahomo.afip.gov.ar/ws/services/LoginCms",
}
MARGEN_DE_VENCIMIENTO = timedelta(minutes=5)


def contexto_ssl():
    """Los servidores de ARCA usan claves DH que OpenSSL rechaza por defecto."""
    contexto = ssl.create_default_context()
    contexto.set_ciphers("DEFAULT@SECLEVEL=1")
    return contexto


def sin_namespaces(xml_texto):
    """Parsea un XML y le quita los namespaces a las etiquetas."""
    raiz = ET.fromstring(xml_texto)
    for elemento in raiz.iter():
        if "}" in elemento.tag:
            elemento.tag = elemento.tag.split("}", 1)[1]
    return raiz


def enviar_soap(url, cuerpo, soap_action, timeout=40):
    """Envía un sobre SOAP y devuelve la respuesta parseada (sin namespaces)."""
    sobre = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        f"<soap:Body>{cuerpo}</soap:Body></soap:Envelope>"
    )
    pedido = urllib.request.Request(
        url,
        data=sobre.encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": soap_action,
        },
    )
    try:
        with urllib.request.urlopen(
            pedido, context=contexto_ssl(), timeout=timeout
        ) as respuesta:
            contenido = respuesta.read()
    except urllib.error.HTTPError as error:
        contenido = error.read()  # los SOAP Fault llegan con HTTP 500
        if not contenido:
            raise
    raiz = sin_namespaces(contenido)
    falla = raiz.find(".//Fault")
    if falla is not None:
        raise FacturacionError(
            "ARCA rechazó el pedido: "
            + (falla.findtext("faultstring") or "error desconocido")
        )
    return raiz


def crear_tra(servicio):
    """Ticket de requerimiento de acceso (TRA) sin firmar."""
    ahora = datetime.now().astimezone()
    desde = (ahora - timedelta(minutes=10)).isoformat(timespec="seconds")
    hasta = (ahora + timedelta(minutes=10)).isoformat(timespec="seconds")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<loginTicketRequest version="1.0"><header>'
        f"<uniqueId>{int(time.time())}</uniqueId>"
        f"<generationTime>{desde}</generationTime>"
        f"<expirationTime>{hasta}</expirationTime>"
        f"</header><service>{servicio}</service></loginTicketRequest>"
    ).encode("utf-8")


def firmar_tra(tra, ruta_certificado, ruta_clave):
    """Firma el TRA (CMS/PKCS#7 con el contenido incluido) y lo devuelve en base64."""
    # pylint: disable=import-outside-toplevel
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs7

    try:
        certificado = x509.load_pem_x509_certificate(Path(ruta_certificado).read_bytes())
        clave = serialization.load_pem_private_key(
            Path(ruta_clave).read_bytes(), password=None
        )
    except (OSError, ValueError, TypeError) as error:
        raise FacturacionError(
            "No se pudo leer el certificado o la clave privada. Revisá los "
            f"archivos en Configuración.\n\n{error}"
        ) from error
    if certificado.not_valid_after_utc < datetime.now().astimezone():
        raise FacturacionError(
            "El certificado digital está vencido. Generá uno nuevo en ARCA."
        )
    try:
        firmado = (
            pkcs7.PKCS7SignatureBuilder()
            .set_data(tra)
            .add_signer(certificado, clave, hashes.SHA256())
            .sign(serialization.Encoding.DER, [])
        )
    except ValueError as error:
        raise FacturacionError(
            "El certificado y la clave privada no se corresponden."
        ) from error
    return base64.b64encode(firmado).decode("ascii")


def _archivo_ticket(ambiente, cuit, servicio):
    return APP_DIR / f"ta_{ambiente}_{cuit}_{servicio}.json"


def _ticket_guardado(archivo):
    try:
        ticket = json.loads(archivo.read_text(encoding="utf-8"))
        vence = datetime.fromisoformat(ticket["vence"])
    except (OSError, ValueError, KeyError):
        return None
    if vence - MARGEN_DE_VENCIMIENTO <= datetime.now().astimezone():
        return None
    return ticket


def obtener_ticket(ambiente, cuit, ruta_certificado, ruta_clave, servicio="wsfe"):
    """Devuelve {"token", "sign"} vigente, pidiendo uno nuevo si hace falta."""
    archivo = _archivo_ticket(ambiente, cuit, servicio)
    ticket = _ticket_guardado(archivo)
    if ticket:
        return ticket

    cms = firmar_tra(crear_tra(servicio), ruta_certificado, ruta_clave)
    try:
        respuesta = enviar_soap(
            URLS[ambiente],
            '<loginCms xmlns="http://wsaa.view.sua.dvadac.desein.afip.gov">'
            f"<in0>{escape(cms)}</in0></loginCms>",
            "",
        )
    except FacturacionError as error:
        texto = str(error)
        if "alreadyAuthenticated" in texto or "ya posee un TA" in texto:
            raise FacturacionError(
                "ARCA ya entregó un ticket de acceso que sigue vigente y esta "
                "computadora no lo tiene guardado. Esperá unos minutos y "
                "volvé a intentarlo."
            ) from error
        if "cms.cert" in texto or "ertificado" in texto:
            raise FacturacionError(
                "ARCA no reconoce el certificado. Verificá que corresponda al "
                f"ambiente elegido ({ambiente}) y que esté asociado al servicio "
                f"de facturación electrónica.\n\nRespuesta de ARCA: {texto}"
            ) from error
        raise

    credenciales = sin_namespaces(respuesta.findtext(".//loginCmsReturn"))
    ticket = {
        "token": credenciales.findtext(".//token"),
        "sign": credenciales.findtext(".//sign"),
        "vence": credenciales.findtext(".//expirationTime"),
    }
    try:
        archivo.write_text(json.dumps(ticket), encoding="utf-8")
    except OSError:
        logger.warning("No se pudo guardar el ticket de acceso en %s", archivo)
    return ticket
