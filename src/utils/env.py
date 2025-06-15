import os
from dotenv import load_dotenv, set_key

def refresh_env():
    """
    Recarga las variables de entorno desde el archivo .env.
    """
    load_dotenv()

def getenv(nombre_variable):
    """
    Obtiene el valor de una variable de entorno. Asegúrate de que las variables
    se hayan recargado antes de usar esta función.

    Args:
        nombre_variable (str): Nombre de la variable de entorno.

    Returns:
        str: Valor de la variable de entorno.
    """
    return os.getenv(nombre_variable)

def update_afip_key(new_value):
    """
    Actualiza la clave AFIP_KEY en el archivo .env.

    Args:
        new_value (str): El nuevo valor para AFIP_KEY.
    """
    set_key('.env', 'AFIP_KEY', new_value)
