# Project Guide: Metadata Capture & Lineage Engine

## 1. Executive Summary
The **Metadata Capture & Lineage Engine** is a specialized backend software system designed to automatically record, track, and visualize data movements across modern data pipelines. By capturing metadata from orchestrators (like Apache Airflow) and parsing static queries, it builds a comprehensive, queryable graph of how data is created, transformed, and consumed within an organization.

## 2. Problem Statement
Modern data pipelines are often completely invisible. When a dashboard displays incorrect metrics, engineers spend days tracing back through dozens of scattered jobs and SQL scripts to uncover where the bad data originated. 
Specific pain points include:
* **Silent Failures:** Schema changes break downstream jobs, and developers have no visibility into who will be affected.
* **Lack of Traceability:** Machine Learning models produce anomalous outputs, and engineers cannot re-trace the origin of the training data.
* **Compliance Risks:** GDPR/HIPAA mandates require full data traceability which doesn't exist out of the box in most data tools.
* **Documentation Decay:** Manual lineage mappings in spreadsheets get abandoned within weeks.

## 3. The Solution
The Lineage Engine solves this by automatically capturing pipeline metadata. Rather than forcing engineers to maintain documentation, the engine sits behind the scenes and listens for events.
1. **Automated Tracking:** An Airflow DAG runs a task, and our system securely captures the lineage in real-time.
2. **Static Parsing:** For code not managed by an orchestrator, SQL queries and dbt manifests can be parsed offline to instantly extract table dependencies.
3. **Graph Retrieval:** All events are structured into an interconnected Graph Database. An engineer can request the full ancestry of a dataset and receive the exact workflow in JSON formatting in under a second.

## 4. System Architecture
The platform is designed around a three-tier architecture:

### A. Ingestion Layer (FastAPI & Pydantic)
* Listens to incoming HTTP POST requests (`/lineage/events`).
* Validates incoming data against the OpenLineage standard using Pydantic.
* Routes the standardized event into the internal processing engine.

### B. Storage & Processing Layer (Neo4j & PostgreSQL)
* **Neo4j (Graph Database):** Acts as the primary Source of Truth for *Topology*. It tracks exactly three relationships: 
  * `[:PRODUCES]` (Job to Dataset)
  * `[:CONSUMES]` (Dataset to Job)
  * `[:HAS_RUN]` (Job to Run execution)
* **PostgreSQL (Relational Database):** Acts as the *Audit Log*. It stores raw logs of the incoming events and run executions, preventing the Graph database from becoming bloated with historical logs.

### C. Retrieval & Visualization Layer (API & React Frontend)
* **REST API:** Exposes endpoints to retrieve downstream impacts (`GET /lineage/downstream`) and upstream ancestry (`GET /lineage/upstream`).
* **Visual Dashboard:** A React/Vite web application that polls the backend and renders the data workflows globally as an interactive node-and-edge Directed Acyclic Graph (DAG) using `React Flow`.

## 5. Technology Stack
* **Language:** Python 3.13
* **Web Framework:** FastAPI (Chosen for async speed and auto-generated API documentation)
* **Graph DB:** Neo4j Community (Optimal for traversal and ancestry queries)
* **Relational DB:** PostgreSQL 15.6 (Optimal for chronological audit logs)
* **Parsers:** SQLGlot (for SQL static analysis), dbt parsers.
* **Infrastructure:** Docker and Docker Compose for DB containerization.
* **Frontend UI:** Vite, React, ReactFlow with TailwindCSS standard.
