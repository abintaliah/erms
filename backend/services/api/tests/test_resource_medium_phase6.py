import os
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from fastapi.testclient import TestClient


def test_database_rejects_past_review_dates_and_unauthorized_location_changes(
    client: TestClient, aggregation: dict,
):
    with pytest.raises(psycopg.errors.RaiseException, match="date_of_next_review_must_be_future"):
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            connection.execute(
                "UPDATE aggregations SET date_of_next_review=CURRENT_TIMESTAMP-INTERVAL '1 minute' WHERE id=%s",
                (aggregation["id"],),
            )

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="location_change_requires_governed_authorization_and_reason",
    ):
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            connection.execute(
                "UPDATE aggregations SET current_location='UNCONTROLLED' WHERE id=%s",
                (aggregation["id"],),
            )


def test_database_vital_protection_cannot_be_bypassed_by_direct_delete(
    client: TestClient, aggregation: dict,
):
    changed = client.post(
        f"/api/v1/aggregations/{aggregation['id']}/vital-status",
        json={"is_vital": True, "reason": "Continuity requirement"},
        headers={"If-Match": str(aggregation["version"])},
    )
    assert changed.status_code == 200, changed.text

    with pytest.raises(psycopg.errors.RaiseException, match="vital_resource_deletion_blocked"):
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            connection.execute("DELETE FROM aggregations WHERE id=%s", (aggregation["id"],))


def test_aggregation_reports_a_direct_vital_record_as_a_vital_descendant(
    client: TestClient, aggregation: dict, record: dict,
):
    changed = client.post(
        f"/api/v1/records/{record['id']}/vital-status",
        json={"is_vital": True, "reason": "Essential evidence"},
        headers={"If-Match": str(record["version"])},
    )
    assert changed.status_code == 200, changed.text

    parent = client.get(f"/api/v1/aggregations/{aggregation['id']}")
    assert parent.status_code == 200, parent.text
    assert parent.json()["has_vital_descendants"] is True


def test_review_dashboard_indexes_exist():
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        indexes = {
            row[0] for row in connection.execute(
                """SELECT indexname FROM pg_indexes
                    WHERE schemaname='public' AND indexname LIKE '%review_due_idx'"""
            ).fetchall()
        }
    assert indexes == {
        "aggregations_review_due_idx",
        "records_review_due_idx",
        "aggregations_owner_review_due_idx",
        "records_owner_review_due_idx",
    }


def test_review_queries_can_use_due_date_and_owner_indexes():
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute("SET LOCAL enable_seqscan=off")
        global_plan = "\n".join(row[0] for row in connection.execute(
            "EXPLAIN SELECT id FROM aggregations WHERE date_of_next_review IS NOT NULL ORDER BY date_of_next_review,id LIMIT 5"
        ))
        owner_plan = "\n".join(row[0] for row in connection.execute(
            "EXPLAIN SELECT id FROM records WHERE owning_org_unit_id=1 AND date_of_next_review IS NOT NULL ORDER BY date_of_next_review,id LIMIT 5"
        ))
    assert "aggregations_review_due_idx" in global_plan
    assert "records_owner_review_due_idx" in owner_plan


def test_concurrent_vital_change_wins_over_delete(client: TestClient, aggregation: dict):
    database_url = os.environ["DATABASE_URL"]
    locker = psycopg.connect(database_url)
    locker.execute("BEGIN")
    locker.execute("SELECT id FROM aggregations WHERE id=%s FOR UPDATE", (aggregation["id"],))

    def attempt_delete() -> str:
        try:
            with psycopg.connect(database_url) as connection:
                connection.execute("DELETE FROM aggregations WHERE id=%s", (aggregation["id"],))
        except psycopg.errors.RaiseException as error:
            return str(error)
        return "deleted"

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending_delete = executor.submit(attempt_delete)
        locker.execute("SELECT set_config('app.vital_status_change_authorized','authorized',true)")
        locker.execute("SELECT set_config('app.change_reason','Continuity decision',true)")
        locker.execute("UPDATE aggregations SET is_vital=true WHERE id=%s", (aggregation["id"],))
        locker.commit()
        outcome = pending_delete.result(timeout=5)
    locker.close()

    assert "vital_resource_deletion_blocked" in outcome
    current = client.get(f"/api/v1/aggregations/{aggregation['id']}")
    assert current.status_code == 200
    assert current.json()["is_vital"] is True
