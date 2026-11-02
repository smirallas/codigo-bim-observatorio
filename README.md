# CÃ³digo BIM Â· recoger-trenes-postgresql

Entrega 2 de la construcciÃ³n del observatorio de datos abiertos.

Requisitos: Docker Compose y Python 3.12 para crear la configuraciÃ³n. Desde `v2`:

    python init_env.py
    docker compose up -d --wait db
    docker compose run --rm --no-deps --build web python lab.py migrate
    docker compose run --rm --no-deps web python lab.py capture rail
    docker compose run --rm --no-deps web python -m unittest discover -s tests -v

Iniciar el recolector con `docker compose --profile live up -d collector`. No hay visor en esta entrega.

No ejecutar otra etiqueta contra un volumen con migraciones posteriores sin revisar compatibilidad. Para comparar entregas en paralelo, utilizar un proyecto Compose distinto (`-p nombre`) y un puerto `LAB_PORT` libre; no borrar volÃºmenes existentes.

[Versiones de los artÃ­culos](VERSIONES.md). CÃ³digo propio MIT; conservar las licencias de bibliotecas y condiciones de las fuentes. No distribuir `.env`, datos recolectados ni copias de bases. Despliegue remoto manual posterior.
