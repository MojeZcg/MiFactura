"""Emisión de facturas automatizando "Comprobantes en línea" de ARCA con Selenium.

Este módulo no toca la interfaz: informa el avance con `on_progress` y los
fallos con `FacturacionError`, así puede ejecutarse en un hilo de trabajo.
"""

import logging
import os
import time
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from config import LOG_DIR, is_debug
from services.comun import (
    NO_EMITIDA,
    SIN_VERIFICAR,
    FacturacionError,
    carpeta_de_descarga,
)

logger = logging.getLogger(__name__)

LOGIN_URL = "https://auth.afip.gob.ar/contribuyente_/login.xhtml"

# Posición de cada opción en los desplegables del formulario de ARCA.
INDICE_TIPO_DOCUMENTO = {"CUIT": 0, "CUIL": 1, "DNI": 6}
INDICE_CONDICION_IVA = {
    "Consumidor Final": 3,
    "Iva Responsable Inscripto": 1,
    "Iva Sujeto Exento": 2,
}
INDICE_UNIDAD_MEDIDA = 7

def start_chrome(download_path):
    """Inicia Chrome. Selenium descarga solo el driver compatible."""
    options = webdriver.ChromeOptions()
    if not is_debug():
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(download_path),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
            "safebrowsing.enabled": True,
        },
    )
    try:
        return webdriver.Chrome(options=options)
    except WebDriverException as error:
        raise FacturacionError(
            "No se pudo abrir Google Chrome. Verificá que esté instalado "
            f"y que haya conexión a internet.\n\n{error.msg}"
        ) from error


def _esperar(driver, condicion, segundos=20):
    return WebDriverWait(driver, segundos).until(condicion)


def _presente(driver, localizador, segundos=20):
    return _esperar(driver, EC.presence_of_element_located(localizador), segundos)


def _click(driver, localizador, segundos=20):
    _esperar(driver, EC.element_to_be_clickable(localizador), segundos).click()


def login(driver):
    """Inicia sesión en ARCA y entra a "Generar Comprobantes"."""
    cuil = os.getenv("ARCA_CUIL")
    clave = os.getenv("ARCA_KEY")
    if not cuil or not clave:
        raise FacturacionError(
            "Faltan el CUIT o la clave fiscal. Cargalos en Configuración."
        )

    driver.get(LOGIN_URL)
    usuario = _presente(driver, (By.ID, "F1:username"))
    usuario.clear()
    usuario.send_keys(cuil, Keys.RETURN)

    campo_clave = _presente(driver, (By.NAME, "F1:password"))
    campo_clave.clear()
    campo_clave.send_keys(clave, Keys.RETURN)

    try:
        _click(driver, (By.CSS_SELECTOR, "a.full-width"), 15)
    except TimeoutException as error:
        raise FacturacionError(
            "ARCA no aceptó el inicio de sesión. Verificá el CUIT y la clave "
            "fiscal en Configuración."
        ) from error

    # El servicio de comprobantes se abre en una pestaña nueva.
    _esperar(driver, lambda d: len(d.window_handles) > 1, 15)
    driver.switch_to.window(driver.window_handles[-1])

    _click(driver, (By.CSS_SELECTOR, 'input[type="button"]'))
    _click(driver, (By.ID, "btn_gen_cmp"))


def put_all_items(driver, products):
    """Carga las líneas de detalle de la factura."""
    for index, product in enumerate(products, start=1):
        _presente(driver, (By.ID, f"detalle_descripcion{index}")).send_keys(
            product["Product"]
        )

        cantidad = _presente(driver, (By.ID, f"detalle_cantidad{index}"))
        cantidad.clear()
        cantidad.send_keys(product["Quantity"])

        Select(_presente(driver, (By.ID, f"detalle_medida{index}"))).select_by_index(
            INDICE_UNIDAD_MEDIDA
        )

        _presente(driver, (By.ID, f"detalle_precio{index}")).send_keys(
            product["Price"]
        )

        if index < len(products):
            _click(
                driver,
                (
                    By.XPATH,
                    '//input[@type="button" and @value="Agregar línea descripción"]',
                ),
            )


def siguiente(driver):
    """Avanza al siguiente paso del formulario."""
    _click(driver, (By.XPATH, '//input[@value="Continuar >"]'))


def esperar_descarga(folder, existentes, timeout=30):
    """Espera un archivo nuevo y completo en `folder`. Devuelve su ruta o None."""
    limite = time.time() + timeout
    while time.time() < limite:
        nuevos = [f for f in folder.iterdir() if f.name not in existentes]
        completos = [
            f for f in nuevos if f.suffix.lower() not in (".tmp", ".crdownload")
        ]
        if completos and len(completos) == len(nuevos):
            return max(completos, key=lambda f: f.stat().st_mtime)
        time.sleep(0.5)
    return None


def _guardar_captura(driver):
    """Guarda una captura del navegador para diagnosticar el fallo."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        ruta = LOG_DIR / f"error_{datetime.now():%Y%m%d_%H%M%S}.png"
        driver.save_screenshot(str(ruta))
        return ruta
    except (WebDriverException, OSError):
        return None


def emitir_factura(tipo_documento, client_id, condicion_iva, products, on_progress=None):
    """Emite una factura en ARCA.

    Args:
        tipo_documento (str): "CUIT", "CUIL" o "DNI".
        client_id (str): Número de documento del cliente (puede ser vacío).
        condicion_iva (str): Condición frente al IVA del cliente.
        products (list): Dicts con 'Product', 'Quantity' y 'Price' (textos).
        on_progress (callable): Recibe (porcentaje, mensaje).

    Returns:
        dict: {"emitida": bool, "pdf": Path | None, "carpeta": Path}

    Raises:
        FacturacionError: si la factura no llegó a emitirse.
    """
    # pylint: disable=too-many-statements
    etapa = "Preparando"

    def paso(porcentaje, mensaje):
        nonlocal etapa
        etapa = mensaje
        logger.info("%s%% %s", porcentaje, mensaje)
        if on_progress:
            on_progress(porcentaje, mensaje)

    carpeta = carpeta_de_descarga()
    paso(3, "Abriendo el navegador")
    driver = start_chrome(carpeta)
    resultado = {"emitida": False, "pdf": None, "carpeta": carpeta}
    confirmacion_enviada = False
    no_emitida, sin_verificar = NO_EMITIDA, SIN_VERIFICAR

    try:
        paso(10, "Iniciando sesión en ARCA")
        login(driver)

        try:
            _click(driver, (By.ID, "novolveramostrar"), 4)
        except TimeoutException:
            pass

        paso(25, "Eligiendo el punto de venta")
        Select(_presente(driver, (By.NAME, "puntoDeVenta"))).select_by_index(1)
        time.sleep(2)  # ARCA carga el tipo de comprobante al elegir el punto de venta
        siguiente(driver)

        paso(35, "Cargando el concepto")
        Select(_presente(driver, (By.ID, "idconcepto"))).select_by_index(1)
        siguiente(driver)

        paso(45, "Cargando los datos del cliente")
        Select(_presente(driver, (By.ID, "idivareceptor"))).select_by_index(
            INDICE_CONDICION_IVA[condicion_iva]
        )
        Select(_presente(driver, (By.ID, "idtipodocreceptor"))).select_by_index(
            INDICE_TIPO_DOCUMENTO[tipo_documento]
        )
        if client_id:
            _presente(driver, (By.ID, "nrodocreceptor")).send_keys(client_id)
        _click(driver, (By.ID, "formadepago1"))
        siguiente(driver)

        paso(60, "Cargando los productos")
        put_all_items(driver, products)
        siguiente(driver)

        if is_debug():
            paso(100, "Simulación terminada (modo DEBUG: no se confirmó)")
            return resultado

        paso(80, "Confirmando la factura")
        existentes = {f.name for f in carpeta.iterdir()}
        confirmacion_enviada = True
        _click(
            driver,
            (By.XPATH, '//input[@type="button" and @value="Confirmar Datos..."]'),
        )
        try:
            _esperar(driver, EC.alert_is_present(), 5)
            driver.switch_to.alert.accept()
        except TimeoutException:
            pass

        boton_imprimir = (By.XPATH, '//input[@type="button" and @value="Imprimir..."]')
        _esperar(driver, EC.element_to_be_clickable(boton_imprimir))
        # Si aparece "Imprimir...", ARCA ya generó el comprobante.
        resultado["emitida"] = True

        paso(90, "Descargando el PDF")
        try:
            driver.find_element(*boton_imprimir).click()
            resultado["pdf"] = esperar_descarga(carpeta, existentes)
        except WebDriverException:
            logger.exception("La factura se emitió pero falló la descarga del PDF")

        paso(100, "Factura emitida")
        return resultado

    except TimeoutException as error:
        captura = _guardar_captura(driver)
        logger.exception("Tiempo de espera agotado en: %s", etapa)
        detalle = f"\n\nCaptura guardada en:\n{captura}" if captura else ""
        raise FacturacionError(
            f"ARCA no respondió como se esperaba en el paso «{etapa}».\n"
            + (sin_verificar if confirmacion_enviada else no_emitida)
            + detalle
        ) from error
    except WebDriverException as error:
        _guardar_captura(driver)
        logger.exception("Error del navegador en: %s", etapa)
        raise FacturacionError(
            f"Falló el navegador en el paso «{etapa}».\n"
            f"{sin_verificar if confirmacion_enviada else no_emitida}\n\n{error.msg}"
        ) from error
    finally:
        driver.quit()
