import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.services.api.main import app
from backend.services.api.authentication import hash_password


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_database(client: TestClient):
    password = "Temporary-Test-Password-123!"
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute("TRUNCATE login_sessions, user_credentials, user_role_assignments, roles, users, org_units, record_draft_components, record_drafts, digital_components, records, aggregations RESTART IDENTITY CASCADE")
        connection.execute("ALTER TABLE event_history DISABLE TRIGGER USER")
        connection.execute("TRUNCATE event_history RESTART IDENTITY")
        connection.execute("ALTER TABLE event_history ENABLE TRIGGER USER")
        org_id = connection.execute("INSERT INTO org_units (code,name) VALUES ('test-root','Test Root') RETURNING id").fetchone()[0]
        user_id = connection.execute("INSERT INTO users (name,email) VALUES ('Test Administrator','admin@test.invalid') RETURNING id").fetchone()[0]
        role_id = connection.execute("INSERT INTO roles (org_unit_id,code,name) VALUES (%s,'system-administrator','System Administrator') RETURNING id", (org_id,)).fetchone()[0]
        connection.execute("INSERT INTO user_role_assignments (user_id,role_id) VALUES (%s,%s)", (user_id,role_id))
        connection.execute("INSERT INTO user_credentials (user_id,password_hash,must_change_password) VALUES (%s,%s,false)", (user_id,hash_password(password)))
    login = client.post("/api/v1/auth/login", json={"email": "admin@test.invalid", "password": password})
    assert login.status_code == 200, login.text
    client.headers["X-CSRF-Token"] = client.cookies.get("erms_csrf")
    yield
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            """
            TRUNCATE
                record_draft_components,
                record_drafts,
                login_sessions,
                user_credentials,
                user_role_assignments,
                roles,
                users,
                org_units,
                digital_components,
                records,
                aggregations
            RESTART IDENTITY CASCADE
            """
        )
        connection.execute("ALTER TABLE event_history DISABLE TRIGGER USER")
        connection.execute("TRUNCATE event_history RESTART IDENTITY")
        connection.execute("ALTER TABLE event_history ENABLE TRIGGER USER")
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)


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
