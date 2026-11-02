FROM python:3.12.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY capturar.py ./
COPY ejemplos ./ejemplos
COPY tests ./tests
CMD ["python", "capturar.py", "--archivo", "ejemplos/posiciones-sinteticas.json"]
