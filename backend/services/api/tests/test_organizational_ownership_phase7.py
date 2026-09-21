import os
import time

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row


def test_production_shaped_subtree_move_is_atomic_audited_and_indexed(client: TestClient):
    source = client.post("/api/v1/aggregations", json={
        "aggregation_number": "P7-SOURCE", "title": "Phase 7 source",
        "classification_id": 1,
    })
    assert source.status_code == 201, source.text
    source = source.json()

    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        user_id = connection.execute(
            "SELECT id FROM users WHERE email='admin@test.invalid'"
        ).fetchone()["id"]
        destination_unit_id = connection.execute(
            "INSERT INTO org_units(code,name) VALUES ('P7-DEST','Phase 7 destination') RETURNING id"
        ).fetchone()["id"]
        destination_role_id = connection.execute(
            "INSERT INTO roles(org_unit_id,code,name) VALUES (%s,'p7-destination','Phase 7 destination') RETURNING id",
            (destination_unit_id,),
        ).fetchone()["id"]
        connection.execute(
            "INSERT INTO user_role_assignments(user_id,role_id) VALUES (%s,%s)",
            (user_id, destination_role_id),
        )

    destination = client.post("/api/v1/aggregations", json={
        "aggregation_number": "P7-DEST", "title": "Phase 7 destination",
        "classification_id": 1, "creator_acl_role_id": destination_role_id,
    })
    assert destination.status_code == 201, destination.text
    destination = destination.json()

    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('app.creator_acl_role_id','1',false)")
        parent_id = source["id"]
        subtree_root_id = None
        aggregation_ids: list[int] = []
        for index in range(150):
            row = connection.execute(
                """INSERT INTO aggregations(parent_aggregation_id,aggregation_number,title)
                   VALUES (%s,%s,%s) RETURNING id""",
                (parent_id, f"P7-NODE-{index:03d}", f"Phase 7 node {index}"),
            ).fetchone()
            parent_id = row["id"]
            subtree_root_id = subtree_root_id or parent_id
            aggregation_ids.append(parent_id)
            connection.execute(
                "INSERT INTO records(aggregation_id,record_number,title) VALUES (%s,%s,%s)",
                (parent_id, f"P7-REC-{index:03d}", f"Phase 7 record {index}"),
            )

    started = time.perf_counter()
    moved = client.post(f"/api/v1/aggregations/{subtree_root_id}/acl-move", json={
        "destination_aggregation_id": destination["id"],
        "resource_version": 1,
        "keep_current_access_as_override": False,
        "confirm_ownership_change": True,
        "reason": "Phase 7 production-shaped subtree move rehearsal",
    })
    elapsed = time.perf_counter() - started
    assert moved.status_code == 200, moved.text
    assert elapsed < 10.0

    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        aggregation_count = connection.execute(
            "SELECT count(*)::int AS count FROM aggregations WHERE id=ANY(%s) AND owning_org_unit_id=%s",
            (aggregation_ids, destination_unit_id),
        ).fetchone()["count"]
        record_count = connection.execute(
            "SELECT count(*)::int AS count FROM records WHERE aggregation_id=ANY(%s) AND owning_org_unit_id=%s",
            (aggregation_ids, destination_unit_id),
        ).fetchone()["count"]
        diagnostics = connection.execute(
            "SELECT count(*)::int AS count FROM organizational_ownership_diagnostics"
        ).fetchone()["count"]
        move_event = connection.execute(
            """SELECT metadata FROM event_history
               WHERE entity_type='aggregation' AND entity_id=%s
                 AND operation='MOVED_WITH_ACL_POLICY' ORDER BY id DESC LIMIT 1""",
            (subtree_root_id,),
        ).fetchone()
        connection.execute("SET enable_seqscan=off")
        aggregation_plan = "\n".join(
            row["QUERY PLAN"] for row in connection.execute(
                "EXPLAIN SELECT id FROM aggregations WHERE owning_org_unit_id=%s AND parent_aggregation_id=%s ORDER BY aggregation_number,id LIMIT 100",
                (destination_unit_id, destination["id"]),
            ).fetchall()
        )
        record_plan = "\n".join(
            row["QUERY PLAN"] for row in connection.execute(
                "EXPLAIN SELECT id FROM records WHERE owning_org_unit_id=%s AND aggregation_id=%s ORDER BY record_number,id LIMIT 100",
                (destination_unit_id, subtree_root_id),
            ).fetchall()
        )

    assert aggregation_count == 150
    assert record_count == 150
    assert diagnostics == 0
    assert move_event["metadata"]["ownership_changed"] is True
    # PostgreSQL may legitimately choose the narrow relationship index plus a
    # small sort, or the ownership-aware browse index, as row widths and
    # statistics evolve. Verify indexed access without pinning a planner choice.
    assert "Index" in aggregation_plan and "Seq Scan" not in aggregation_plan
    assert "parent_aggregation_id" in aggregation_plan
    assert "Index" in record_plan and "Seq Scan" not in record_plan
    assert "aggregation_id" in record_plan

    reconciliation = client.get("/api/v1/security-operations/reconciliation")
    assert reconciliation.status_code == 200, reconciliation.text
    assert reconciliation.json()["ownership_invariant_violation_count"] == 0
