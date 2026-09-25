import os
import psycopg
from fastapi.testclient import TestClient

from backend.services.api.tests.test_phase7_mutation_authorization import (
    PASSWORD, _grant_principal, _login_as_phase7, _set_aggregation_acl,
    _set_record_acl,
)


def _set_governance(role_id: int) -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute("UPDATE roles SET is_information_governance=true WHERE id=%s", (role_id,))


def test_drafts_are_private_and_commit_rechecks_current_policy(client: TestClient, aggregation: dict):
    _, role_id = _grant_principal({"record.create", "aggregation.view"})
    _login_as_phase7(client)
    draft = client.post("/api/v1/record-drafts", json={
        "aggregation_id": aggregation["id"], "record_number": "DRAFT-P8", "title": "Private",
    })
    assert draft.status_code == 201
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    login = client.post("/api/v1/auth/login", json={
        "email": "admin@test.invalid", "password": "Temporary-Test-Password-123!",
    })
    assert login.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies.get("erms_csrf")
    assert client.get(f"/api/v1/record-drafts/{draft.json()['id']}").status_code == 404

    _login_as_phase7(client)
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            """DELETE FROM profile_privileges WHERE profile_id=(SELECT profile_id FROM roles WHERE id=%s)
               AND privilege_id=(SELECT id FROM privileges WHERE code='record.create')""", (role_id,),
        )
    denied = client.post(f"/api/v1/record-drafts/{draft.json()['id']}/commit")
    assert denied.status_code == 403
    assert client.get(f"/api/v1/record-drafts/{draft.json()['id']}").status_code == 403
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        assert connection.execute(
            "SELECT status FROM record_drafts WHERE id=%s", (draft.json()["id"],),
        ).fetchone()[0] == "open"


def test_record_create_covers_staged_components_but_not_post_commit_changes(
    client: TestClient, aggregation: dict,
):
    _, role_id = _grant_principal({"aggregation.view", "record.view", "record.create"})
    _set_aggregation_acl(
        aggregation["id"], role_id, {"aggregation.view", "aggregation.add_record"},
    )
    _login_as_phase7(client)

    draft = client.post("/api/v1/record-drafts", json={
        "aggregation_id": aggregation["id"],
        "record_number": "DRAFT-PACKAGE-P8",
        "title": "Record creation package",
    })
    assert draft.status_code == 201, draft.text
    staged = client.post(
        f"/api/v1/record-drafts/{draft.json()['id']}/components",
        data={"component_order": 1},
        files={"file": ("created-with-record.txt", b"created with record", "text/plain")},
    )
    assert staged.status_code == 201, staged.text

    committed = client.post(f"/api/v1/record-drafts/{draft.json()['id']}/commit")
    assert committed.status_code == 201, committed.text
    record = committed.json()

    # Grant visibility to the resulting resource, but no mutation permission.
    # This isolates the post-commit privilege boundary from record concealment.
    _set_record_acl(record["id"], role_id, {"record.view"})
    current = client.get(f"/api/v1/records/{record['id']}")
    assert current.status_code == 200, current.text
    assert client.patch(
        f"/api/v1/records/{record['id']}",
        json={"title": "Forbidden metadata change"},
        headers={"If-Match": str(current.json()["version"])},
    ).status_code == 403
    assert client.post(
        f"/api/v1/records/{record['id']}/digital-components/upload",
        data={"component_order": 2},
        files={"file": ("post-commit.txt", b"forbidden", "text/plain")},
    ).status_code == 403

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        components = connection.execute(
            "SELECT file_name FROM digital_components WHERE record_id=%s ORDER BY component_order",
            (record["id"],),
        ).fetchall()
    assert [row[0] for row in components] == ["created-with-record.txt"]


def test_component_replace_is_atomic_and_not_implied_by_add_or_remove(
    client: TestClient, record: dict,
):
    component = client.post(
        f"/api/v1/records/{record['id']}/digital-components/upload",
        data={"component_order": 1}, files={"file": ("before.txt", b"before", "text/plain")},
    ).json()
    _, role_id = _grant_principal({
        "record.view", "record.component.add", "record.component.remove",
        "record.component.list", "record.component.download",
    })
    _set_record_acl(record["id"], role_id, {
        "record.view", "record.component.list", "record.component.download",
        "record.component.add", "record.component.remove",
    })
    _login_as_phase7(client)
    denied = client.put(
        f"/api/v1/digital-components/{component['id']}/content",
        headers={"If-Match": str(component["version"])},
        files={"file": ("after.txt", b"after", "text/plain")},
    )
    assert denied.status_code == 403
    assert client.get(f"/api/v1/digital-components/{component['id']}/content").content == b"before"


def test_metadata_only_record_viewer_cannot_enumerate_or_read_components(
    client: TestClient, record: dict,
):
    component = client.post(
        f"/api/v1/records/{record['id']}/digital-components/upload",
        data={"component_order": 1}, files={"file": ("hidden.txt", b"hidden", "text/plain")},
    ).json()
    _, role_id = _grant_principal({"record.view"})
    _set_record_acl(record["id"], role_id, {"record.view"})
    _login_as_phase7(client)
    assert client.get("/api/v1/digital-components", params={"record_id": record["id"]}).json() == []
    assert client.get(f"/api/v1/digital-components/{component['id']}").status_code == 404
    assert client.get(f"/api/v1/digital-components/{component['id']}/content").status_code == 404


def test_component_preview_does_not_imply_print_authorization(
    client: TestClient, record: dict,
):
    component = client.post(
        f"/api/v1/records/{record['id']}/digital-components/upload",
        data={"component_order": 1},
        files={"file": ("view-only.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    ).json()
    _, role_id = _grant_principal({
        "record.view", "record.component.view", "record.component.list",
    })
    _set_record_acl(record["id"], role_id, {
        "record.view", "record.component.view", "record.component.list",
    })
    _login_as_phase7(client)
    assert client.get(
        f"/api/v1/digital-components/{component['id']}/rendition"
    ).status_code == 200
    denied = client.get(
        f"/api/v1/digital-components/{component['id']}/print-rendition"
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "insufficient_resource_permission"


def test_governance_correction_into_closed_aggregation_preserves_closure_and_audits(
    client: TestClient, aggregation: dict, record: dict,
):
    destination = client.post("/api/v1/aggregations", json={
        "aggregation_number": "P8-CLOSED", "title": "Closed destination", "classification_id": 1,
    }).json()
    closed = client.patch(
        f"/api/v1/aggregations/{destination['id']}",
        json={"date_closed": destination["date_created"]},
        headers={"If-Match": str(destination["version"])},
    ).json()
    _, role_id = _grant_principal({
        "aggregation.view", "record.view", "record.move", "closure.correct_record_placement",
    })
    _set_governance(role_id)
    _set_record_acl(record["id"], role_id, {"record.view", "record.move"})
    _login_as_phase7(client)
    current_record = client.get(f"/api/v1/records/{record['id']}").json()
    correction = client.post(
        f"/api/v1/records/{record['id']}/correct-placement",
        json={"destination_aggregation_id": destination["id"]},
        headers={"If-Match": str(current_record["version"]), "X-Change-Reason": "Correct filing error"},
    )
    assert correction.status_code == 200, correction.text
    assert correction.json()["aggregation_id"] == destination["id"]
    assert client.get(f"/api/v1/aggregations/{destination['id']}").json()["date_closed"] == closed["date_closed"]
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        event = connection.execute(
            """SELECT operation,reason,metadata FROM event_history
               WHERE entity_type='record' AND entity_id=%s
                 AND operation='CLOSED_AGGREGATION_RECORD_CORRECTED'""", (record["id"],),
        ).fetchone()
    assert event[0] == "CLOSED_AGGREGATION_RECORD_CORRECTED"
    assert event[1] == "Correct filing error"
    assert event[2]["closure_date_unchanged"] is True
    assert event[2]["governance_roles"]
