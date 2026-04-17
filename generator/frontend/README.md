# Frontend (Vite + React)

Part of the generator service. Sources live here; the production build
is served as static files by the generator's Flask app (at `/`) and
produced by the generator's Dockerfile.

## Dev

    npm install
    VITE_GENERATOR_URL=http://localhost:5002 VITE_EDGE_URL=http://localhost:5003 npm run dev

Vite proxies `/api/*` to the Flask app at :5002.

## Build

    npm run build
    # produces dist/ which is copied into generator/src/static/ by the Docker build
