# MiFactura

MiFactura es una aplicación para emitir facturas electrónicas a través de los servicios web de la ARCA (La Agencia de Recaudación y Control Aduanero de Argentina).

[![GPLv3 License](https://img.shields.io/badge/License-GPL%20v3-yellow.svg)](https://opensource.org/licenses/)

## Screenshots

<p align="center">
  <img src="screenshots/Screenshot_1.png" alt="Main App Screenshot" width="450">
  <img src="screenshots/Screenshot_2.png" alt="History window Screenshot" >
</p>

## Como ejecutar localmente

Clone the project

```bash
  git clone git@github.com:MojeZcg/FacturaFacilARCA.git
  cd MiFactura
```

Create an enviroment and activate it

```bash
  py -3.12 -m venv venv
  .\venv\Scripts\activate
```

Or Linux or Mac.

```bash
  py -3.12 -m venv venv
  source venv/bin/activate
```

Install dependencies

```bash
  pip install -r .\requirements.txt
```

Start the app (the database is created by running main.py)

```bash
  py src/main.py
```

## Como Desplegar

Para desplegar, debe generar un archivo .spec con pyinstaller

```bash
  pyinstaller --onefile --windowed --name MiFactura --icon=src/static/arca.ico --add-data "src/static:static" --add-data "LICENSE:." src/main.py
```

## Configuración

La primera vez que se abre, la app pide los datos y los guarda en un archivo `.env` junto a la aplicación (ver `.env.example`). Se pueden cambiar después desde **Configuración**.

Hay dos formas de emitir, elegibles en la pestaña **General**:

### Navegador automático

Automatiza "Comprobantes en línea" con Selenium. Solo necesita el CUIT y la clave fiscal, y Google Chrome instalado (Selenium descarga el driver automáticamente).

### API de ARCA (WSFEv1)

Pide el CAE directamente al web service de ARCA y genera el PDF con su código QR. Es más rápida y no depende de la página web. Sirve para monotributistas (Factura C) y responsables inscriptos (Factura A a otros responsables inscriptos, Factura B al resto). Los precios cargados se toman como finales, con IVA incluido.

Preparación, una sola vez:

1. En **Configuración → API de ARCA**, usar "generar clave y pedido" para crear la clave privada (`.key`) y el pedido de certificado (`.csr`).
2. En ARCA, **Administración de Certificados Digitales**: agregar un alias, subir el `.csr` y descargar el certificado (`.crt`).
3. En **Administrador de Relaciones**: asociar el servicio "Facturación Electrónica" (`wsfe`) a ese certificado.
4. En **Administración de puntos de venta y domicilios**: crear un punto de venta de tipo "RECE para aplicativo y web services".
5. Cargar en la app el certificado, el punto de venta y los datos del emisor.

Para probar sin validez fiscal existe el ambiente de **Homologación**, que usa certificados propios generados desde el servicio "WSASS" de ARCA.

### Modo de prueba

Con `DEBUG=1` en el `.env` no se emite nada: el motor web muestra el navegador y frena antes de confirmar; el motor API se autentica y consulta la numeración, pero no pide el CAE.

Si una emisión falla, el detalle queda en `logs/app.log`.

## Ejecutar Lint

Para ejecutar el lint, instale las dependencias y pylint.

```bash
  pip -r requirements.txt
  pip install pylint
```

luego ejecuta pylint.

```bash
  pylint **/*.py
```

## Contribuciones

¡Las contribuciones siempre son bienvenidas!

Consulte `contributing.md` para conocer las formas de contribuir.

Siga el `code of conduct` de este proyecto.

#### Para empezar:

1. Hacer un fork del repositorio.
2. Crear una nueva rama con tu funcionalidad o corrección:

```bash
git checkout -b nueva-funcionalidad
```

3. Hacer commit de los cambios:

```bash
git commit -am 'Añadir nueva funcionalidad'
```

4. Push:

```bash
git push origin nueva-funcionalidad
```

5. Crear un Pull Request en GitHub.

## Licencia

#### Este proyecto está bajo la Licencia [GPL v3](https://www.gnu.org/licenses/gpl-3.0.en.html#license-text). Para más detalles, ver el archivo [LICENSE](LICENSE).
