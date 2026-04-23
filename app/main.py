import os
import socket
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.ingestion.router import router as ingestion_router
from app.api.router import router as query_router

app = FastAPI(
    title="Metadata Lineage Engine",
    description="Captures and exposes data lineage across pipelines.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingestion_router)
app.include_router(query_router)


def _tcp_probe(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a TCP port is accepting connections. Fast, non-blocking."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@app.get("/health", tags=["system"])
def health_check():
    """
    Lightweight health check using raw TCP probes.
    Does NOT create DB driver sessions — avoids hangs and cache issues.
    """
    neo4j_ok = _tcp_probe("127.0.0.1", 7687)
    postgres_ok = _tcp_probe("127.0.0.1", 5432)

    status = {
        "neo4j": "ok" if neo4j_ok else "starting",
        "postgres": "ok" if postgres_ok else "starting",
    }
    all_ok = neo4j_ok and postgres_ok
    return {
        "status": "healthy" if all_ok else "degraded",
        "services": status
    }