# PolCRM - obraz produkcyjny (waitress). Użycie z PostgreSQL: docker compose up -d (zob. docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    APP_HOST=0.0.0.0 \
    APP_PORT=4666

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Aplikacja nie działa jako root; zapisuje tylko do instance/ i output/ (wolumeny).
RUN useradd --create-home --uid 10001 polcrm \
    && mkdir -p instance output \
    && chown -R polcrm:polcrm instance output
USER polcrm

EXPOSE 4666
CMD ["python", "app.py"]
