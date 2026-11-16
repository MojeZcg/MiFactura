"""Genera la clave privada y el pedido de certificado (CSR) que se sube a ARCA."""

from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from config import APP_DIR

CARPETA = APP_DIR / "certificados"


def generar_clave_y_pedido(cuit, organizacion, alias="mifactura"):
    """Crea <alias>_<fecha>.key y .csr. Nunca pisa una clave existente.

    Returns:
        tuple[Path, Path]: rutas de la clave privada y del pedido (CSR).
    """
    CARPETA.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_clave = CARPETA / f"{alias}_{marca}.key"
    ruta_pedido = CARPETA / f"{alias}_{marca}.csr"

    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pedido = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, organizacion),
                    x509.NameAttribute(NameOID.COMMON_NAME, alias),
                    x509.NameAttribute(NameOID.SERIAL_NUMBER, f"CUIT {cuit}"),
                ]
            )
        )
        .sign(clave, hashes.SHA256())
    )

    ruta_clave.write_bytes(
        clave.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    ruta_pedido.write_bytes(pedido.public_bytes(serialization.Encoding.PEM))
    return ruta_clave, ruta_pedido
