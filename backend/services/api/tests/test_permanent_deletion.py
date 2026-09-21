import os
import time

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from backend.services.api.continuity_lock import acquire_continuity_lock


def _headers(version: int, reason: str = "Created in error") -> dict[str, str]:
    return {"If-Match": str(version), "X-Change-Reason": reason}


def test_user_preflight_delete_cascades_and_preserves_audit(client: TestClient):
    user = client.post("/api/v1/users", json={"name": "Temporary Person", "email": "temporary@test.invalid"}).json()
    preflight = client.get(f"/api/v1/users/{user['id']}/deletion-preflight")
    assert preflight.status_code == 200
    assert preflight.json()["allowed"] is True

    response = client.delete(f"/api/v1/users/{user['id']}", headers=_headers(user["version"]))
    assert response.status_code == 204
    assert client.get(f"/api/v1/users/{user['id']}").status_code == 404
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        event = connection.execute(
            "SELECT before_state,reason FROM event_history WHERE entity_type='user' AND entity_id=%s AND operation='DELETE'",
            (user["id"],),
        ).fetchone()
        assert event is not None
        assert event[0]["email"] == "temporary@test.invalid"
        assert event[1] == "Created in error"


def test_self_and_reserved_entities_are_blocked(client: TestClient):
    me = client.get("/api/v1/auth/me").json()["user"]
    report = client.get(f"/api/v1/users/{me['id']}/deletion-preflight").json()
    assert "self_deletion" in {item["code"] for item in report["blockers"]}
    response = client.delete(f"/api/v1/users/{me['id']}", headers=_headers(1))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "deletion_blocked"

    role = client.get("/api/v1/roles", params={"limit": 50}).json()[0]
    response = client.delete(f"/api/v1/roles/{role['id']}", headers=_headers(role["version"]))
    assert response.status_code == 409
    assert "reserved_role" in {item["code"] for item in response.json()["detail"]["blockers"]}

    unit = client.get("/api/v1/org-units", params={"limit": 50}).json()[0]
    response = client.delete(f"/api/v1/org-units/{unit['id']}", headers=_headers(unit["version"]))
    assert response.status_code == 409
    assert "org_unit_has_roles" in {item["code"] for item in response.json()["detail"]["blockers"]}


def test_role_dependencies_are_reported_and_then_role_can_be_deleted(client: TestClient):
    unit = client.post("/api/v1/org-units", json={"code": "TMP", "name": "Temporary Unit"}).json()
    role = client.post("/api/v1/roles", json={"org_unit_id": unit["id"], "code": "TMP-R", "name": "Temporary Role"}).json()
    subordinate = client.post("/api/v1/roles", json={
        "org_unit_id": unit["id"], "supervisor_role_id": role["id"], "code": "TMP-S", "name": "Temporary Subordinate",
    }).json()
    report = client.get(f"/api/v1/roles/{role['id']}/deletion-preflight").json()
    assert report["allowed"] is False
    assert "supervises_roles" in {item["code"] for item in report["blockers"]}

    changed = client.patch(
        f"/api/v1/roles/{subordinate['id']}", json={"supervisor_role_id": None},
        headers={"If-Match": str(subordinate["version"])},
    )
    assert changed.status_code == 200
    assert client.delete(f"/api/v1/roles/{role['id']}", headers=_headers(role["version"])).status_code == 204
    assert client.delete(f"/api/v1/roles/{subordinate['id']}", headers=_headers(changed.json()["version"])).status_code == 204
    unit = client.get(f"/api/v1/org-units/{unit['id']}").json()
    assert client.delete(f"/api/v1/org-units/{unit['id']}", headers=_headers(unit["version"])).status_code == 204


def test_stale_delete_rolls_back_without_cascading(client: TestClient):
    user = client.post("/api/v1/users", json={"name": "Concurrent Person", "email": "concurrent@test.invalid"}).json()
    changed = client.patch(
        f"/api/v1/users/{user['id']}", json={"name": "Concurrent Person Updated"},
        headers={"If-Match": str(user["version"])},
    ).json()
    response = client.delete(f"/api/v1/users/{user['id']}", headers=_headers(user["version"]))
    assert response.status_code == 412
    assert client.get(f"/api/v1/users/{user['id']}").json()["version"] == changed["version"]


def test_continuity_coordination_does_not_lock_tables_or_unrelated_writes(client: TestClient):
    with (
        psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as holder,
        psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as other,
    ):
        acquire_continuity_lock(holder)
        heavy_locks = holder.execute(
            """SELECT count(*) AS count FROM pg_locks
               WHERE pid=pg_backend_pid() AND locktype='relation'
                 AND mode IN ('ShareRowExclusiveLock','ExclusiveLock','AccessExclusiveLock')"""
        ).fetchone()["count"]
        assert heavy_locks == 0

        other.execute("SET LOCAL statement_timeout='750ms'")
        started = time.perf_counter()
        other.execute("INSERT INTO users(name,email) VALUES ('Unrelated Writer','writer@test.invalid')")
        assert time.perf_counter() - started < 0.75

        # A participating continuity mutation waits rather than racing the
        # deletion decision, proving coordination is narrow and intentional.
        try:
            acquire_continuity_lock(other)
        except psycopg.errors.QueryCanceled:
            other.rollback()
        else:  # pragma: no cover - would indicate the two transactions did not coordinate
            raise AssertionError("continuity advisory lock did not serialize participants")


def test_deletion_preflight_latency_at_requested_scale(client: TestClient):
    """5,000 users, 10 roles, 100 aggregations, and two records per aggregation."""
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        root = connection.execute("SELECT id FROM org_units WHERE code='test-root'").fetchone()["id"]
        profile = connection.execute("SELECT id FROM profiles WHERE code='ALL_PRIVS'").fetchone()["id"]
        baseline = connection.execute("SELECT id FROM security_levels ORDER BY level_number,id LIMIT 1").fetchone()["id"]
        role_ids = [row["id"] for row in connection.execute(
            """INSERT INTO roles(org_unit_id,code,name,profile_id,security_level_id)
               SELECT %s,'PERF-R-'||n,'Performance Role '||n,%s,%s FROM generate_series(1,10) n
               RETURNING id""", (root, profile, baseline),
        ).fetchall()]
        user_ids = [row["id"] for row in connection.execute(
            """INSERT INTO users(name,email)
               SELECT 'Performance User '||n,'performance-'||n||'@test.invalid'
               FROM generate_series(1,5000) n RETURNING id"""
        ).fetchall()]
        connection.execute(
            """INSERT INTO user_role_assignments(user_id,role_id)
               SELECT user_id,(%s::bigint[])[((row_number() OVER (ORDER BY user_id)-1)%%10)+1]
               FROM unnest(%s::bigint[]) user_id""", (role_ids, user_ids),
        )
        aggregation_ids = [row["id"] for row in connection.execute(
                """INSERT INTO aggregations(
                       aggregation_number,title,classification_id,owning_org_unit_id
                   )
                   SELECT 'PERF-A-'||n,'Performance Aggregation '||n,1,%s
                   FROM generate_series(1,100) n RETURNING id""", (root,)
            ).fetchall()]
        connection.execute(
            """INSERT INTO records(aggregation_id,record_number,title)
               SELECT aggregation_id,'PERF-RC-'||aggregation_id||'-'||n,
                      'Performance Record '||aggregation_id||'-'||n
               FROM unnest(%s::bigint[]) aggregation_id CROSS JOIN generate_series(1,2) n""",
            (aggregation_ids,),
        )

    started = time.perf_counter()
    for user_id in user_ids[:5]:
        response = client.get(f"/api/v1/users/{user_id}/deletion-preflight")
        assert response.status_code == 200
    for role_id in role_ids[:5]:
        response = client.get(f"/api/v1/roles/{role_id}/deletion-preflight")
        assert response.status_code == 200
    elapsed = time.perf_counter() - started
    assert elapsed < 5.0, f"10 scaled deletion preflights took {elapsed:.3f}s"
