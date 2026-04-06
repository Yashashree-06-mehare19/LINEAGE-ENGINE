import os
import psycopg2
from neo4j import GraphDatabase
from functools import lru_cache


@lru_cache(maxsize=1)
def get_neo4j_driver():
    uri = os.environ["NEO4J_URI"]
    user = os.environ["NEO4J_USER"]
    password = os.environ["NEO4J_PASSWORD"]
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver


def get_postgres_conn():
    dsn = os.environ["POSTGRES_DSN"]
    return psycopg2.connect(dsn)