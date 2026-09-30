import warnings

import pytest

from backend.services.api.main import app


@pytest.fixture(autouse=True)
def clean_database():
    """OpenAPI generation is pure and must not depend on a test database."""
    yield


def test_openapi_operation_ids_are_unique():
    app.openapi_schema = None

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        schema = app.openapi()

    duplicate_operation_warnings = [
        warning
        for warning in caught
        if "Duplicate Operation ID" in str(warning.message)
    ]
    assert duplicate_operation_warnings == []

    operation_ids = [
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))


def test_content_head_routes_are_not_documented_as_duplicate_operations():
    app.openapi_schema = None
    schema = app.openapi()

    for suffix in ("content", "rendition", "print-rendition"):
        path = f"/api/v1/digital-components/{{component_id}}/{suffix}"
        operations = schema["paths"][path]
        assert "get" in operations
        assert "head" not in operations

        registered_methods = {
            method
            for route in app.routes
            if getattr(route, "path", None) == path
            for method in getattr(route, "methods", set())
        }
        assert {"GET", "HEAD"} <= registered_methods
