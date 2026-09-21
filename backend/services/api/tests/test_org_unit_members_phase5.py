import os

import psycopg
from fastapi.testclient import TestClient


def _org_members(*permissions: str) -> dict:
    return {
        "principal_type": "org_unit_members",
        "role_id": None,
        "permission_codes": list(permissions),
    }


def test_org_unit_members_is_supported_by_every_acl_scope(
    client: TestClient, aggregation: dict, record: dict,
):
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute("UPDATE roles SET is_information_governance=true WHERE id=1")

    aggregation_acl = client.get(
        f"/api/v1/aggregations/{aggregation['id']}/permissions",
    ).json()
    replaced = client.put(
        f"/api/v1/aggregations/{aggregation['id']}/permissions",
        json={
            "version": aggregation_acl["resource_acl_version"],
            "grants": [_org_members("aggregation.view")],
            "reason": "Test contextual aggregation principal",
        },
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["override_acl"] == [{
        "principal_type": "org_unit_members",
        "role_id": None,
        "display_name": "All org unit members",
        "role_code": None,
        "permission_codes": ["aggregation.view"],
    }]

    child_default = client.get(
        f"/api/v1/aggregations/{aggregation['id']}/default-child-aggregation-permissions",
    ).json()
    child_replaced = client.put(
        f"/api/v1/aggregations/{aggregation['id']}/default-child-aggregation-permissions",
        json={
            "version": child_default["version"],
            "mode": "custom",
            "grants": [_org_members("aggregation.view")],
            "reason": "Test contextual child aggregation principal",
        },
    )
    assert child_replaced.status_code == 200, child_replaced.text
    assert child_replaced.json()["effective_acl"][0]["principal_type"] == "org_unit_members"

    record_default = client.get(
        f"/api/v1/aggregations/{aggregation['id']}/default-child-record-permissions",
    ).json()
    record_default_replaced = client.put(
        f"/api/v1/aggregations/{aggregation['id']}/default-child-record-permissions",
        json={
            "version": record_default["version"],
            "grants": [_org_members("record.view")],
            "reason": "Test contextual child record principal",
        },
    )
    assert record_default_replaced.status_code == 200, record_default_replaced.text
    assert record_default_replaced.json()["effective_acl"][0]["principal_type"] == "org_unit_members"

    record_acl = client.get(f"/api/v1/records/{record['id']}/permissions").json()
    record_replaced = client.put(
        f"/api/v1/records/{record['id']}/permissions",
        json={
            "version": record_acl["resource_acl_version"],
            "inherit_acl_from_parent": False,
            "grants": [_org_members("record.view")],
            "reason": "Test contextual record principal",
        },
    )
    assert record_replaced.status_code == 200, record_replaced.text
    assert record_replaced.json()["effective_acl"][0]["display_name"] == "All org unit members"


def test_org_unit_members_tracks_effective_membership_without_acl_rewrites(
    client: TestClient, aggregation: dict, record: dict,
):
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            "DELETE FROM aggregation_acl_grants WHERE aggregation_id=%s",
            (aggregation["id"],),
        )
        connection.execute(
            """INSERT INTO aggregation_acl_grants(
                   aggregation_id,principal_type,permission_id
               ) SELECT %s,'org_unit_members',id FROM permissions
                 WHERE code='aggregation.view'""",
            (aggregation["id"],),
        )
        connection.execute(
            "DELETE FROM aggregation_child_record_acl_defaults WHERE aggregation_id=%s",
            (aggregation["id"],),
        )
        connection.execute(
            """INSERT INTO aggregation_child_record_acl_defaults(
                   aggregation_id,principal_type,permission_id
               ) SELECT %s,'org_unit_members',id FROM permissions
                 WHERE code='record.view'""",
            (aggregation["id"],),
        )
        outsider_unit = connection.execute(
            "INSERT INTO org_units(code,name) VALUES ('OUT','Outside') RETURNING id",
        ).fetchone()[0]
        owner_unit = aggregation["owning_org_unit_id"]
        profile_id, level_id = connection.execute(
            "SELECT profile_id,security_level_id FROM roles WHERE id=1",
        ).fetchone()
        outsider_user = connection.execute(
            "INSERT INTO users(name,email) VALUES ('Outside User','outside@example.test') RETURNING id",
        ).fetchone()[0]
        outsider_role = connection.execute(
            """INSERT INTO roles(org_unit_id,profile_id,security_level_id,code,name)
               VALUES (%s,%s,%s,'OUT-R','Outside Role') RETURNING id""",
            (outsider_unit, profile_id, level_id),
        ).fetchone()[0]
        assignment = connection.execute(
            """INSERT INTO user_role_assignments(user_id,role_id)
               VALUES (%s,%s) RETURNING id""",
            (outsider_user, outsider_role),
        ).fetchone()[0]

        assert not connection.execute(
            "SELECT user_has_aggregation_permission(%s,%s,'aggregation.view')",
            (outsider_user, aggregation["id"]),
        ).fetchone()[0]
        assert not connection.execute(
            "SELECT user_has_record_permission(%s,%s,'record.view')",
            (outsider_user, record["id"]),
        ).fetchone()[0]

        connection.execute(
            "UPDATE roles SET org_unit_id=%s WHERE id=%s", (owner_unit, outsider_role),
        )
        assert connection.execute(
            "SELECT user_has_aggregation_permission(%s,%s,'aggregation.view')",
            (outsider_user, aggregation["id"]),
        ).fetchone()[0]
        assert connection.execute(
            "SELECT user_has_record_permission(%s,%s,'record.view')",
            (outsider_user, record["id"]),
        ).fetchone()[0]

        connection.execute(
            "UPDATE user_role_assignments SET valid_until=CURRENT_TIMESTAMP WHERE id=%s",
            (assignment,),
        )
        assert not connection.execute(
            "SELECT user_has_record_permission(%s,%s,'record.view')",
            (outsider_user, record["id"]),
        ).fetchone()[0]


def test_org_unit_members_principal_shape_and_reserved_role_identity(
    client: TestClient, aggregation: dict,
):
    acl = client.get(f"/api/v1/aggregations/{aggregation['id']}/permissions").json()
    invalid_shape = client.put(
        f"/api/v1/aggregations/{aggregation['id']}/permissions",
        json={
            "version": acl["resource_acl_version"],
            "grants": [{
                "principal_type": "org_unit_members",
                "role_id": 1,
                "permission_codes": ["aggregation.view"],
            }],
            "reason": "Invalid contextual principal",
        },
    )
    assert invalid_shape.status_code == 422

    reserved_code = client.post(
        "/api/v1/roles",
        json={
            "org_unit_id": aggregation["owning_org_unit_id"],
            "code": "org_unit_members",
            "name": "Impersonating role",
        },
    )
    assert reserved_code.status_code == 422
