# Lineage Engine

Lineage Engine is a metadata lineage tracking system. It visualizes and tracks data flows and relationships across datasets, pipelines, and transformation jobs using a graph-based approach to map how data moves from source to destination.

## Features

- Interactive Lineage Graphs: Visualizes data pipelines as Directed Acyclic Graphs (DAGs).
- Column-Level Lineage: Traces column-to-column transformations to determine origin and impact.
- Pipeline Integration: Supports integration with various data pipelines, including dbt and Apache Airflow via OpenLineage.

## Tech Stack

- Frontend: React (Vite, Tailwind, React Flow)
- Backend: Python (FastAPI)
- Databases: Neo4j (Graph data), PostgreSQL (Relational logs and config)
- Infrastructure: Docker, Docker Compose, Apache Airflow

## Project Structure

- `app/`: FastAPI backend
- `frontend/`: React web application
- `infra/`: Infrastructure initialization (e.g., Postgres scripts)
- `scripts/`: Testing and data simulation scripts
- `airflow_dags/`: Example Airflow DAGs for OpenLineage integration
- `docker-compose.yml`: Local infrastructure configuration

## Setup Instructions

### 1. Start Infrastructure
Start Neo4j, Postgres, and Airflow containers using Docker Compose.

```bash
docker-compose up -d
```

### 2. Run Backend
Navigate to the project root, install dependencies, and start the FastAPI server. 

```bash
pip install -r requirements.txt
cd app
uvicorn main:app --reload --port 8000
```
Ensure your `.env` file is properly configured.

### 3. Run Frontend
In a separate terminal, install node modules and start the development server.

```bash
cd frontend
npm install
npm run dev
```

### 4. Access the Application
Open `http://localhost:5173` in your browser. 
You can run `python run_live_demo.py` to seed sample pipelines and data into the Neo4j graph for testing.

## Testing

Run tests located in the `scripts/` directory:

```bash
python scripts/test_stage10.py
```

## Documentation

Refer to `implementation_plan.md` for information on ongoing features and architecture planning.
