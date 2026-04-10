import os
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


@app.get("/health", tags=["system"])
def health_check():
    status = {"neo4j": "unknown", "postgres": "unknown"}

    try:
        from app.db_client import get_neo4j_driver
        driver = get_neo4j_driver()
        with driver.session() as session:
            session.run("RETURN 1")
        status["neo4j"] = "ok"
    except Exception as e:
        status["neo4j"] = f"error: {str(e)}"

    try:
        from app.db_client import get_postgres_conn
        conn = get_postgres_conn()
        conn.close()
        status["postgres"] = "ok"
    except Exception as e:
        status["postgres"] = f"error: {str(e)}"

    all_ok = all(v == "ok" for v in status.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "services": status
    }