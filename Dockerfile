FROM python:3.11-slim AS backend
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY scripts scripts
RUN useradd --create-home app && mkdir runtime && chown app:app runtime
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn","backend.app.main:app","--host","0.0.0.0","--port","8000","--workers","1","--no-access-log"]

