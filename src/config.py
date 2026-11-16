"""Rutas, constantes y configuración compartida de MiFactura."""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv, set_key


def resource_path(relative_path):
    """Ruta absoluta de un recurso, tanto en desarrollo como en PyInstaller."""
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base_path / relative_path


def _app_dir():
    """Carpeta donde viven los datos de la app (.env, History.db, logs)."""
    override = os.getenv("MIFACTURA_HOME")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_DIR = _app_dir()
ENV_PATH = APP_DIR / ".env"
DB_PATH = APP_DIR / "History.db"
LOG_DIR = APP_DIR / "logs"
ICON_PATH = resource_path("static/arca.ico")

THEME = "bootstrap-light"
DEFAULT_DOWNLOAD_PATH = Path.home() / "Documents" / "MisFacturas"

CLAVES_COMUNES = ("ARCA_CUIL", "DOWNLOAD_PATH")
CLAVES_POR_MOTOR = {
    "web": ("ARCA_KEY",),
    "api": ("ARCA_PTO_VTA", "ARCA_CERT", "ARCA_PRIVATE_KEY"),
}


def load_env():
    """(Re)carga el archivo .env de la aplicación."""
    load_dotenv(ENV_PATH, override=True)


def is_configured():
    """True si existen todas las variables que necesita el motor elegido."""
    motor = "api" if os.getenv("ARCA_MOTOR") == "api" else "web"
    return all(os.getenv(key) for key in CLAVES_COMUNES + CLAVES_POR_MOTOR[motor])


def is_debug():
    """En modo DEBUG el navegador es visible y la factura no se confirma."""
    return os.getenv("DEBUG", "0") == "1"


def save_settings(valores):
    """Guarda en el .env las variables de `valores` (las que valen None se omiten)."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    ENV_PATH.touch(exist_ok=True)
    for clave, valor in valores.items():
        if valor is not None:
            set_key(ENV_PATH, clave, str(valor))
    load_env()


def setup_logging():
    """Registra la actividad en logs/app.log para poder diagnosticar fallos."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
