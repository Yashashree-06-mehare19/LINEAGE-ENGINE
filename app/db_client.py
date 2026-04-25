import os
import psycopg2
from neo4j import GraphDatabase
from functools import lru_cache


@lru_cache(maxsize=1)
def get_neo4j_driver():
    uri = os.environ["NEO4J_URI"]
    user = os.environ["NEO4J_USER"]
    password = os.environ["NEO4J_PASSWORD"]
    driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=3)
    driver.verify_connectivity()
    return driver


def get_postgres_conn():
    dsn = os.environ["POSTGRES_DSN"]
    return psycopg2.connect(dsn, connect_timeout=3)


def apply_neo4j_constraints():
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.run("CREATE CONSTRAINT job_name_unique IF NOT EXISTS FOR (j:Job) REQUIRE j.name IS UNIQUE")
        session.run("CREATE CONSTRAINT dataset_uri_unique IF NOT EXISTS FOR (d:Dataset) REQUIRE d.uri IS UNIQUE")
        session.run("CREATE CONSTRAINT run_id_unique IF NOT EXISTS FOR (r:Run) REQUIRE r.run_id IS UNIQUE")
        session.run("CREATE INDEX dataset_tags_index IF NOT EXISTS FOR (d:Dataset) ON (d.tags)")