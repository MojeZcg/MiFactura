"""Utilidades de formato y validación compartidas."""


def solo_digitos(texto):
    """Devuelve únicamente los dígitos de un texto."""
    return "".join(ch for ch in texto if ch.isdigit())


def formatear_cuit(digitos):
    """Formatea hasta 11 dígitos como XX-XXXXXXXX-X."""
    digitos = digitos[:11]
    partes = [digitos[0:2], digitos[2:10], digitos[10:11]]
    return "-".join(parte for parte in partes if parte)


def cuit_valido(digitos):
    """Valida un CUIT/CUIL de 11 dígitos con su dígito verificador."""
    if len(digitos) != 11 or not digitos.isdigit():
        return False
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    suma = sum(int(d) * p for d, p in zip(digitos, pesos))
    verificador = 11 - suma % 11
    if verificador == 11:
        verificador = 0
    return verificador == int(digitos[10])


def parsear_numero(texto):
    """Convierte '1.500,50', '1500,5' o '1500.5' a float. Lanza ValueError."""
    texto = texto.strip().replace("$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return float(texto)


def numero_a_texto(valor):
    """Número sin ceros sobrantes y con punto decimal (formato del formulario)."""
    return f"{valor:.2f}".rstrip("0").rstrip(".")


def formatear_pesos(valor):
    """Formatea un importe al estilo argentino: $ 1.234,50."""
    texto = f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"$ {texto}"
