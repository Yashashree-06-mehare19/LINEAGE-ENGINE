import os
import socket
import urllib.request
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.ingestion.router import router as ingestion_router
from app.api.router import router as query_router
from app.api.column_router import router as column_router   # Stage 10

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
app.include_router(column_router)     # Stage 10: column-level lineage endpoints


@app.on_event("startup")
def startup_event():
    from app.db_client import apply_neo4j_constraints
    try:
        apply_neo4j_constraints()
        print("Neo4j constraints and indexes applied successfully.")
    except Exception as e:
        print(f"Failed to apply Neo4j constraints (Neo4j might be down/starting): {e}")


def _tcp_probe(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a TCP port is accepting connections. Fast, non-blocking."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _neo4j_http_probe(host: str = "127.0.0.1", port: int = 7474, timeout: float = 3.0) -> bool:
    """
    Check Neo4j readiness via HTTP on port 7474.

    Why HTTP 7474 and NOT TCP 7687?
    - Port 7687 (Bolt) opens ~30s BEFORE Neo4j can serve queries.
      A TCP probe on 7687 returns True while the engine is still booting — a false positive.
    - Port 7474 (Neo4j HTTP browser) only returns HTTP 200 when the full
      server is initialized and ready to accept Bolt connections.
    - So 7474 = accurate readiness signal. 7687 = premature open.
    """
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=timeout):
            return True
    except Exception:
        return False


@app.get("/health", tags=["system"])
def health_check():
    """
    Lightweight health check.
    - Neo4j: HTTP probe on port 7474 (accurate — only 200 when fully ready)
    - Postgres: TCP probe on port 5432
    Does NOT create DB driver sessions — avoids hangs and lru_cache issues.
    """
    neo4j_ok = _neo4j_http_probe()
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