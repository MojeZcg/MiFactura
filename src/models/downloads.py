import threading
import time
import os

from tkinter.messagebox import showinfo, showerror
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from services.afip_client import start_chrome, login, realizar_operacion
from gui.progress import ProgressWindow
from utils.files import delete_files_with_parentheses


def download_day(driver):
    """
    Descarga las facturas del día desde la página de AFIP y las guarda en el
    directorio predefinido.

    Args:
        driver (WebDriver): La instancia del controlador de Chrome.
    """
    progress = ProgressWindow(None, 'Descarga del Dia')
    try:
        login(driver)

        progress.set_progress(20)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "btn_consultas"))
        ).click()

        dropdown = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "idTipoComprobante"))
        )
        progress.set_progress(40)

        drselect = Select(dropdown)
        drselect.select_by_index(9)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, '//input[contains(@value, "Buscar")]')
            )
        ).click()

        progress.set_progress(55)

        try:
            ver_buttons = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located(
                    (By.XPATH, '//input[contains(@value, "Ver")]')
                )
            )
        except RuntimeError as e:
            progress.stop_progress()
            showinfo(
                title='Descargar Facturas',
                message='Hoy no hay facturas para descargar.',
            )
            print(f'Error: {e}')

        progress.set_progress(70)


        for button in ver_buttons:
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(button)
            ).click()

            time.sleep(4)

        time.sleep(3)

        delete_files_with_parentheses(os.getenv('DOWNLOAD_PATH'))

        progress.set_progress(100)
        progress.stop_progress()

    except RuntimeError as e:
        showerror(
            title='Descarga del dia',
            message=f'Ocurrio un error: {e}'
        )
    finally:
        progress.stop_progress()


def download_in_thread():
    """
    Inicia una nueva instancia del navegador Chrome y descarga las facturas del
    día en un hilo separado.
    """
    driver = start_chrome()
    thread = threading.Thread(target=download_day, args=(driver,))
    thread.start()



def in_thread(client_option, client_id, option, products):
    """
    Realiza una operación en un hilo separado y muestra la ventana de progreso.

    Args:
        client_option (int): La opción del cliente.
        client_id (str): El identificador del cliente.
        option (int): La opción seleccionada.
        products (list): La lista de productos.
    """
    driver = start_chrome()

    debug = False # Cambia a True si necesitas depurar

    thread = threading.Thread(
        target=realizar_operacion,
        args=(driver, client_option, client_id, option, products, debug,)
    )
    thread.start()
