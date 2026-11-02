FROM python:3.12.13-slim
WORKDIR /app
COPY v2/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd -u 10001 -m lab && mkdir -p /var/cache/observatorio && chown lab:lab /var/cache/observatorio
COPY v2 ./v2
USER lab
WORKDIR /app/v2
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
EXPOSE 8027
HEALTHCHECK --interval=10s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8027/v2/api/health',timeout=3)"
CMD ["python","server.py"]
