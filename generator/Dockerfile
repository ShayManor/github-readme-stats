# --- stage 1: build the React SPA ---
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_GENERATOR_URL=""
ARG VITE_EDGE_URL=""
ENV VITE_GENERATOR_URL=$VITE_GENERATOR_URL
ENV VITE_EDGE_URL=$VITE_EDGE_URL
RUN npm run build

# --- stage 2: python runtime ---
FROM python:3.11-slim AS runtime
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
RUN mkdir -p /app/src/static /app/data
COPY --from=frontend-build /app/frontend/dist/ /app/src/static/

EXPOSE 5002
ENV GENERATOR_SETTINGS_DB_PATH=/app/data/settings.db
ENV GENERATOR_WIDGETS_DB_PATH=/app/data/widgets.db

CMD ["gunicorn", "-b", "0.0.0.0:5002", "-w", "2", "src.api:app"]
