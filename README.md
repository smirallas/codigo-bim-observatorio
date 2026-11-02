# CÃ³digo BIM Â· evaluar-datos-aproximaciones

Entrega 6 de la construcciÃ³n del observatorio de datos abiertos.

Requisitos: Docker Compose y Python 3.12 para crear la configuraciÃ³n. Desde `v2`:

    python init_env.py
    docker compose up -d --wait db
    docker compose run --rm --no-deps --build web python lab.py migrate
    docker compose run --rm --no-deps web python lab.py capture rail
    docker compose run --rm --no-deps web python -m unittest discover -s tests -v

    docker compose --profile live up -d --build --wait

Visor local: http://127.0.0.1:8042/v2/. Solo fuentes reales, actualizaciÃ³n automÃ¡tica y ficha al pulsar el mapa. No incluye consulta histÃ³rica pÃºblica. PostgreSQL no publica puerto; la web escucha en localhost. Sin datos disponibles, la web muestra esa ausencia. No usar los ejemplos como posiciones reales.

Para importar geometrÃ­as nacionales, descargar el GeoPackage y conservar su ZIP original desde CNIG. Montarlos como archivos de entrada y ejecutar `python lab.py import-roads-gpkg /datos/red.gpkg --original /datos/red.zip --kind railway`. El WMS de referencia no importa las geometrÃ­as. Sin esta carga, la ficha indica cobertura no disponible. Los archivos nacionales no se distribuyen en Git.

El perfil live recoge tambiÃ©n el horario GTFS por coincidencias exactas. Un horario planificado no mide puntualidad.

Prueba interna de la pregunta ferroviaria: `docker compose run --rm --no-deps web python lab.py report`. Los escenarios son sintÃ©ticos y no aparecen en el visor pÃºblico.

No ejecutar otra etiqueta contra un volumen con migraciones posteriores sin revisar compatibilidad. Para comparar entregas en paralelo, utilizar un proyecto Compose distinto (`-p nombre`) y un puerto `LAB_PORT` libre; no borrar volÃºmenes existentes.

[Versiones de los artÃ­culos](VERSIONES.md). CÃ³digo propio MIT; conservar las licencias de bibliotecas y condiciones de las fuentes. No distribuir `.env`, datos recolectados ni copias de bases. Despliegue remoto manual posterior.
