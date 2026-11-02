# Leer datos de trenes · primera entrega práctica

Un comando descarga una sola respuesta JSON de posiciones de Renfe, conserva sus bytes y resume la presencia y validez de coordenadas, velocidad y hora individual. También funciona sin red con un ejemplo sintético. No arranca la aplicación completa ni necesita una base de datos.

Requisitos: Python 3.12 o Docker. Solo utiliza la biblioteca estándar. Abre la terminal en esta carpeta.

## Empezar sin consultar la fuente

```powershell
python capturar.py --archivo ejemplos/posiciones-sinteticas.json
```

En Windows puedes sustituir `python` por `py -3.12`; en Linux, por `python3`. El ejemplo tiene tres vehículos sintéticos: una velocidad cero válida, una ausente y una negativa inválida. El resumen esperado es:

```json
"speed_m_s": {"valido": 1, "ausente": 1, "invalido": 1}
```

## Descargar una respuesta real

```powershell
python capturar.py
```

Consulta una sola vez https://gtfsrt.renfe.com/vehicle_positions_LD.json. El número de vehículos y los campos disponibles pueden cambiar. No se instala un recolector periódico ni se hacen consultas desde un navegador de lector.

Cada ejecución crea una carpeta nueva en `data/raw/lecturas/`:

- `original.json`: bytes de la respuesta completa, conservados incluso si no son un JSON válido.
- `manifest.json`: procedencia, intento, recepción cuando existe, metadatos HTTP, tamaño, SHA-256 y resumen o error.

Una descarga fallida deja un manifiesto de error; no produce un resumen vacío que pueda confundirse con cero vehículos. Se limita la lectura a 15 MB y el tiempo de espera a 20 segundos. Si supera el tamaño, no guarda la respuesta truncada como si fuese el original completo. La hora de recepción es propia; `feed_timestamp` es el valor de la cabecera y `observed_at` cuenta timestamps individuales presentes y válidos. No se sustituyen unos por otros. Este inspector comprueba estructura y campos seleccionados; no certifica toda la especificación GTFS ni la coherencia temporal de cada observación.

Para volver a analizar un original, sin red:

```powershell
python capturar.py --archivo data/raw/lecturas/CARPETA_DE_LA_CAPTURA/original.json
```

## Probar en Docker

```powershell
docker build -t codigo-bim-leer-trenes:local .
docker run --rm codigo-bim-leer-trenes:local
docker run --rm codigo-bim-leer-trenes:local python -m unittest discover -s tests -v
```

La primera ejecución usa el ejemplo sintético. Para conservar una descarga real fuera del contenedor, crea `capturas` y monta esa carpeta. En PowerShell:

```powershell
New-Item -ItemType Directory -Force capturas | Out-Null
docker run --rm --mount "type=bind,source=$((Get-Location).Path)/capturas,target=/capturas" codigo-bim-leer-trenes:local python capturar.py --salida /capturas
```

En Linux, el mismo montaje se puede expresar como `--mount "type=bind,source=$(pwd)/capturas,target=/capturas"`, creando antes la carpeta con `mkdir -p capturas`.

## Pruebas en Python

```powershell
python -m unittest discover -s tests -v
```

Nueve casos comprueban HTTP correcto/error, fallo de red, bytes y huella, carpetas independientes, datos ausentes/erróneos, límites de tamaño y separación de horas. El HTTP de pruebas es un servidor local; no llama a Renfe.

## Fuentes y licencia

Código MIT, con el aviso de autoría incluido en LICENSE. El ejemplo de `ejemplos/` es sintético y forma parte de este código. Los originales descargados no se distribuyen en el paquete.

Fuente real: Renfe Data, [posiciones AV, LD y MD](https://data.renfe.com/es/dataset/posicion-vehiculos-av-ld-md), que enlaza el recurso JSON e indica CC BY 4.0. Las condiciones de los datos son independientes de la licencia del programa. Para interpretar campos, consultar la [referencia GTFS Realtime](https://gtfs.org/documentation/realtime/reference/).

## Continuación

La siguiente entrega persistirá capturas y registros normalizados en PostgreSQL, con PostGIS cuando se incorporen geometrías. El visor previsto es MapLibre GL JS con capas independientes. Este incremento no contiene SQLite ni incorpora todavía base de datos, visor o conectores DGT, meteorológicos o de vuelos.
