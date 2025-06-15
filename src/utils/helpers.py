def center_window(window):
    """
    Centra una ventana de tkinter en la pantalla.

    Args:
        window (ttk.Window): La instancia de la ventana de tkinter.
    """
    window.update_idletasks()

    width = window.winfo_width()
    height = window.winfo_height()

    x_offset = (window.winfo_screenwidth() - width) // 2
    y_offset = (window.winfo_screenheight() - height) // 2

    window.geometry(f'+{x_offset}+{y_offset}')
