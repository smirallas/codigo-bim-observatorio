# Laboratorio de datos abiertos · versión 2.6 · AEMET local

## Visor público live

La interfaz pública muestra únicamente fuentes reales y su estado actual. Se actualiza cada 30 segundos mientras la página está visible y al volver a ella; el recolector central consulta cada proveedor con su intervalo independiente. No hay selector de simulaciones, consulta histórica, búsqueda de registros ni panel de notas del laboratorio. La ficha se abre pulsando un elemento del mapa. Se conservan atribuciones, unidades, tiempos y errores relevantes junto a la capa o al dato.

Trenes es la vista inicial; Carreteras/DGT, Aviones y Meteorología tienen capas y leyendas propias. Las categorías tienen casillas y Todas/Ninguna. Los filtros se pueden apagar conservando su valor, y sus selecciones sobreviven al cambio de pestaña y al refresco. La navegación se deriva del catálogo incluido en cada entrega; no habilita fuentes ausentes mediante la URL.

La API pública rechaza parámetros de disponibilidad histórica, predicción puntual histórica y modos de demostración. Los escenarios y la reproducción siguen disponibles como herramientas y pruebas locales del desarrollador, sin controles ni rutas de simulación en la web pública. La persistencia interna no ofrece un navegador histórico al visitante.

La cobertura ferroviaria conectada corresponde a Renfe AV/LD/MD. La aplicación no monitoriza toda la circulación ni implementa una gestión completa de incidencias ferroviarias reales.

Pruebas: `tests/groups.cjs` recorre categorías, filtros, pestañas, móvil, teclado, clic en una posición y refresco de 30 segundos. Utiliza metadatos meteorológicos controlados y una muestra reducida de una posición real para aislar el clic; estas comprobaciones no sustituyen la verificación independiente del proveedor.

PostgreSQL/PostGIS, reproducción ferroviaria y visor MapLibre por capas. Conectores centrales de Renfe, carreteras OpenStreetMap, incidencias DGT DATEX II 3.7, posiciones ADSB.lol y mapas de predicción AEMET HARMONIE-AROME. OpenSky queda como proveedor opcional. Independiente de Autodesk y de Issues Manager. Sin cuentas ni datos personales del lector.

La aplicación es un mapa a pantalla completa, con controles plegables a la izquierda y fichas a la derecha. Incluye filtros y colores por servicio ferroviario, operador publicado, categoría o modelo de aeronave y tipo, causa o provincia de las incidencias. «Sin dato» se conserva como categoría: no se deducen operadores a partir del indicativo de un vuelo ni se asigna un servicio a un tren por semejanza de números.

Los trazados IGN-CNIG se importan también como geometrías en PostGIS. Las imágenes WMS siguen sirviendo de contexto visual. La búsqueda de tramos utiliza las geometrías importadas, no los píxeles del WMS. Los mapas de temperatura, precipitación de la hora previa y velocidad del viento proceden de GeoTIFF oficiales AEMET HARMONIE-AROME para Península/Baleares y Canarias. DWD y el punto MET Norway no participan en el recorrido activo.

## Arrancar en Docker

Desde esta carpeta, con Python 3.12 y Docker Compose:

```powershell
python init_env.py
docker compose up -d --build --wait
```

`init_env.py` crea una contraseña aleatoria en `.env` y se niega a sobrescribir un archivo existente. No compartas ese archivo. Abrir http://127.0.0.1:8042/v2/. El puerto publicado escucha solo en localhost; PostgreSQL no publica puerto. El volumen `observatorio-pg` es exclusivo de este laboratorio. Sin el perfil live no se recolectan posiciones. El modo archivo actual sí puede consultar las imágenes WMS a través del servidor; los ejemplos sintéticos funcionan sin acceso a proveedores. El primer build sí descarga dependencias e imágenes; la ejecución de ejemplos utiliza recursos servidos localmente.

El prototipo antiguo y `/v1/` permanecen en su carpeta e imagen anteriores. Esta versión no los sustituye por un servidor incompatible. No hace falta arrancar el prototipo para seguir las nuevas entregas.

## Utilizar el visor

Abrir la página, elegir el ámbito y activar sus capas y categorías. Para ver detalles, pulsar directamente sobre un elemento. El mapa ocupa toda la ventana; los controles y la ficha se integran en laterales plegables. Los datos sin hora individual conservan esa ausencia y las capturas antiguas se señalan. Una posición publicada no identifica automáticamente una vía física.

## Consultar proveedores una sola vez

```powershell
docker compose run --rm --no-deps web python lab.py capture rail
docker compose run --rm --no-deps web python lab.py capture roads
docker compose run --rm --no-deps web python lab.py capture dgt
docker compose run --rm --no-deps web python lab.py capture flights
docker compose run --rm --no-deps web python lab.py capture weather
```

Los errores se registran por fuente y no borran su captura anterior. `status: error` no significa cero incidencias. Los paquetes AEMET idénticos se reconocen por su huella y no se vuelven a archivar. Los reintentos no se generan desde la interfaz.

Para activar el recolector periódico, revisa primero las fuentes, sus límites y el área. Añade en `.env` `ENABLED_SOURCES=rail,dgt,flights,weather,weather_maps,schedule` y ejecuta:

```powershell
docker compose --profile live up -d collector
```

Los ciclos son independientes: Renfe y ADSB.lol cada 60 s, DGT cada 120 s, paquetes de mapas AEMET cada hora y horario GTFS cada 6 h. Hay una pequeña dispersión aleatoria, hasta cuatro trabajos simultáneos y espera creciente tras errores. `RAIL_INTERVAL`, `DGT_INTERVAL`, `FLIGHTS_INTERVAL`, `WEATHER_INTERVAL` y `WEATHER_MAPS_INTERVAL` se configuran en `.env`; los mínimos del proveedor y los mínimos del código prevalecen. El origen puntual antiguo `weather` se ignora, incluso si sigue en una configuración anterior. Las carreteras son referencia: no se descargan en este bucle. Parar el recolector con `docker compose stop collector` conserva el archivo.

El visor consulta al servidor cada 30 s mientras la página está visible y al volver a ella. No provoca una consulta al proveedor por cada lector. Mantiene filtros, encuadre y selección; una ficha se sigue solo si la identidad del elemento es unívoca. Si no lo es, conserva los tiempos anteriores y avisa. Recepción reciente no equivale a observación reciente.

El perfil recomendado para live habilita `ENABLED_SOURCES=rail,dgt,flights,weather,weather_maps,schedule`. Una configuración anterior que contenga solo `rail` debe actualizarse explícitamente. El recolector tiene su propio control de salud por latido, independiente del servidor HTTP.

## Tramos nacionales en PostGIS

Descargar los GeoPackage nacionales de [ferrocarril](https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec=13139375) y [carreteras](https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec=13139379) del CNIG. Esta versión se contrastó con la edición 07/2026. La cobertura de carreteras es nacional, pero no incluye todo el viario urbano, caminos y carriles bici de los paquetes provinciales. Conservar sus atribuciones: obra derivada de IGR-RT 2026, CC-BY 4.0 scne.es.

Guardar los ZIP y sus GeoPackage extraídos en `data/raw/networks`, fuera del paquete público. Montar esa carpeta como `/raw` en el contenedor, en solo lectura, y ejecutar:

```text
python lab.py import-roads-gpkg /raw/cnig-carreteras-2026-07.gpkg --original /raw/cnig-carreteras-2026-07.zip
python lab.py import-roads-gpkg /raw/cnig-ferrocarril-2026-07.gpkg --original /raw/cnig-ferrocarril-2026-07.zip --kind railway
```

El nombre del comando es común a ambos tipos mediante `--kind`. Lee el GeoPackage oficial con `sqlite3` en modo lectura, porque ese es el formato de distribución: la aplicación sigue guardando todo en PostgreSQL/PostGIS. Transforma EPSG:4258 a EPSG:4326, descarta la dimensión vertical en el análisis horizontal y conserva el ZIP original en bloques BYTEA con sus hashes. Deduplica por identificador de tramo y guarda todos los registros de carreteras o líneas asociadas, evitando confundir esos alias con vías paralelas. Una carga parcial o fallida no se utiliza para asociar posiciones. El importador WFS queda disponible para consultas acotadas; una discrepancia de recuentos impide declararlo completo.

La ficha consulta hasta ocho candidatos en 120 m, con distancia geodésica. Si hay varios dentro de 25 m adicionales respecto al más próximo, indica ambigüedad. Distingue red no disponible, ausencia de candidato, enlace ficticio y tramo cartográfico próximo. Es una búsqueda geométrica exploratoria, no un ajuste de trayectorias: precisión GPS desconocida, vías dobles, cruces y paralelismos impiden confirmar la vía física. No rellena `track_id` ni habilita el motor de alcance. Una incidencia DGT puede aportar la coordenada de un extremo de su localización lineal; la búsqueda no identifica automáticamente todos los tramos afectados.

`/api/features/{source}/{capture_id}/{ordinal}` devuelve la entidad exacta, su captura, horario cuando procede y candidatos con el identificador de la importación. El corte histórico excluye capturas y redes que aún no estaban disponibles. `python verify_networks.py` contrasta recuentos, geometrías, originales y muestras reales sin consultar proveedores.

## Mapas meteorológicos

Las tres capas raster se activan por separado y conservan opacidad, validez y escala. Se descargan los dos paquetes oficiales desde `https://www.aemet.es/es/api-eltiempo/modelos/download/harmonie/PB` y `/CAN`, sin clave OpenData. El navegador consulta únicamente el servidor local. Rasterio reproyecta EPSG:4326 a teselas EPSG:3857 con vecino más próximo, conservando los colores originales; no se interpolan magnitudes a partir de imágenes coloreadas. El paquete validado se archiva en PostgreSQL y la caché raster regenerable se limita a 256 MiB.

La validez procede de `FECHA` y la escala de `ESCALA` en cada GeoTIFF. La actualización de archivos procede del mtime del paquete; no se presenta como salida del modelo, que no se identifica en estos archivos. Se conservan ambas regiones y la recepción por separado. La lluvia corresponde a la hora previa en mm; el viento es velocidad en km/h, sin atribuirle las barbas del antiguo DWD. Son predicciones, no radar ni observaciones. Los dominios se validan antes de sustituir la captura disponible y los errores no producen una malla ficticia.

## Herramientas internas de archivo y pruebas

```powershell
docker compose run --rm --no-deps web python lab.py snapshot rail
docker compose run --rm --no-deps web python lab.py snapshot rail --at 2026-11-01T15:30:00Z
docker compose run --rm --no-deps web python lab.py report
```

La consulta histórica puede devolver `null` si aún no se había recibido una captura. El almacén confirma original, huella, normalización y geometrías en una transacción. Usa `timestamptz`, JSONB, BYTEA y geometrías EPSG:4326 con índice GiST. Las migraciones llevan huella y bloqueo para impedir aplicar dos veces una versión o modificar silenciosamente una ya aplicada. Retención del recolector: siete días y un máximo de 10.080 capturas por fuente. Una copia anterior a la retención puede ser necesaria para investigaciones históricas.

La regla de alcance utiliza el motor versionado del proyecto. Exige vía declarada, sentido compatible, tiempos, velocidad e incertidumbre suficientes. No se aplica a vuelos, carreteras ni meteorología por compartir un mapa. No genera comunicaciones externas.

## Pruebas

```powershell
docker compose run --rm --no-deps web python -m unittest discover -s tests -v
```

Las pruebas usan identificadores `test-...` y limpian únicamente sus capturas. No destruyen el volumen ni sobrescriben fuentes reales. Para el navegador, desde la carpeta padre `experimento-ferroviario`:

```powershell
docker build -f v2/tests/Dockerfile.browser -t codigo-bim-observatorio-browser:local .
```

Crea `v2/artifacts` y ejecuta la imagen con la red `codigo-bim-observatorio_default`, montando esa carpeta en `/artifacts`. El README de verificación conserva el comando exacto utilizado. El contenedor recorre la UI live, categorías, filtros, cambios de pestaña, clic, actualización automática y móvil a 390 y 360 px; guarda capturas y JSON. Esas pruebas locales no acreditan HTTPS ni el iframe de WordPress del futuro servidor.

## Licencias y despliegue

Código propio MIT. MapLibre BSD-3-Clause; sus módulos, licencia e integridad npm se incluyen en `web/`. Natural Earth: dominio público; procedencia, versión y selección en `web/geography-provenance.json`. Los paquetes excluyen `.env`, bases, originales de terceros y capturas con registros reales. Véanse [fuentes](fuentes.md) y [despliegue manual](despliegue.md).
