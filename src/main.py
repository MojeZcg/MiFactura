"""Punto de entrada de MiFactura."""

import ttkbootstrap as ttk

from config import THEME, is_configured, load_env, setup_logging


def main():
    """Inicia la aplicación (y la configuración inicial si hace falta)."""
    setup_logging()
    load_env()

    # Se importan después de cargar la configuración.
    from gui.app import App  # pylint: disable=import-outside-toplevel
    from gui.dialogs import SettingsDialog  # pylint: disable=import-outside-toplevel
    from models.database import (  # pylint: disable=import-outside-toplevel
        inicializar_si_necesario,
    )

    inicializar_si_necesario()

    root = ttk.Window(title="MiFactura", themename=THEME)

    if not is_configured():
        root.withdraw()
        dialogo = SettingsDialog(root, primera_vez=True)
        root.wait_window(dialogo)
        if not dialogo.guardado:
            root.destroy()
            return
        root.deiconify()

    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
