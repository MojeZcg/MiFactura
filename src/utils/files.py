import os

def delete_files_with_parentheses(directory):
    """
    Elimina archivos con paréntesis en sus nombres dentro de un directorio
    especificado.

    Args:
        directory (str): La ruta del directorio donde se buscarán los archivos.
    """
    for filename in os.listdir(directory):
        if '(' in filename or ')' in filename:
            file_path = os.path.join(directory, filename)
            try:
                os.remove(file_path)
            except OSError as e:
                print(f"Error deleting {file_path}: {e}")
