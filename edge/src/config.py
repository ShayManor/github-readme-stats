import os

PORT = int(os.getenv("EDGE_PORT", "5003"))
GENERATOR_URL = os.getenv("GENERATOR_URL", "http://localhost:5002")
CACHE_TYPE = os.getenv("CACHE_TYPE", "SimpleCache")
CACHE_REDIS_URL = os.getenv("CACHE_REDIS_URL", "")
CACHE_DEFAULT_TIMEOUT = int(os.getenv("CACHE_DEFAULT_TIMEOUT", "86400"))
CACHE_THRESHOLD = int(os.getenv("CACHE_THRESHOLD", "10000"))
UPSTREAM_TIMEOUT = int(os.getenv("EDGE_UPSTREAM_TIMEOUT", "10"))
