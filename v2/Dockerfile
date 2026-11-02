FROM python:3.12.13-slim
WORKDIR /app
COPY v2/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd -u 10001 -m lab && mkdir -p /var/cache/observatorio && chown lab:lab /var/cache/observatorio
COPY v2 ./v2
USER lab
WORKDIR /app/v2
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
EXPOSE 8027
CMD ["python","lab.py","migrate"]
