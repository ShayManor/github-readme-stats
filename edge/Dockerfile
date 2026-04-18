FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src

EXPOSE 5003
# Bind to $PORT when set (e.g. Cloud Run injects PORT=8080); default to 5003.
CMD ["sh", "-c", "exec gunicorn -b 0.0.0.0:${PORT:-5003} -w 2 src.api:app"]
