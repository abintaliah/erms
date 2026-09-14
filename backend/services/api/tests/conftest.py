import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.services.api.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_database(client: TestClient):
    yield
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            "TRUNCATE digital_components, records, aggregations RESTART IDENTITY CASCADE"
        )


@pytest.fixture
def aggregation(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/aggregations",
        json={"aggregation_number": "AGG-001", "title": "Root aggregation"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def record(client: TestClient, aggregation: dict) -> dict:
    response = client.post(
        "/api/v1/records",
        json={
            "aggregation_id": aggregation["id"],
            "record_number": "REC-001",
            "title": "Example record",
        },
    )
    assert response.status_code == 201
    return response.json()
