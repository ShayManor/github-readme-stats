FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
RUN mkdir -p /app/data

EXPOSE 5001
ENV FETCHER_DB_PATH=/app/data/fetcher.db

# Default is the API. Override CMD for cron: ["python", "-m", "src.cron"]
CMD ["gunicorn", "-b", "0.0.0.0:5001", "-w", "2", "src.api:app"]
