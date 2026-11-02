# CÃ³digo BIM Â· leer-datos-trenes

Entrega 1 de la construcciÃ³n del observatorio de datos abiertos.

Primera lectura de una fuente. Abrir `primeros-pasos/README.md`.

    docker build -t codigo-bim-leer-trenes:local primeros-pasos
    docker run --rm codigo-bim-leer-trenes:local python -m unittest discover -s tests -v
    docker run --rm codigo-bim-leer-trenes:local

La ejecuciÃ³n predeterminada utiliza un ejemplo identificado como sintÃ©tico. Para descargar Renfe y conservar el original, seguir el README de primeros-pasos. No hay todavÃ­a base de datos ni visor.

No ejecutar otra etiqueta contra un volumen con migraciones posteriores sin revisar compatibilidad. Para comparar entregas en paralelo, utilizar un proyecto Compose distinto (`-p nombre`) y un puerto `LAB_PORT` libre; no borrar volÃºmenes existentes.

[Versiones de los artÃ­culos](VERSIONES.md). CÃ³digo propio MIT; conservar las licencias de bibliotecas y condiciones de las fuentes. No distribuir `.env`, datos recolectados ni copias de bases. Despliegue remoto manual posterior.
