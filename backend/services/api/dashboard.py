from datetime import datetime

from fastapi import APIRouter, Depends, Query
from psycopg import Connection

from .authentication import Principal, principal_from_request
from .database import get_connection
from .schemas import DashboardSummaryRead


router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryRead)
def dashboard_summary(
    recent_limit: int = Query(7, ge=1, le=50),
    recent_since: datetime | None = None,
    principal: Principal = Depends(principal_from_request),
    connection: Connection = Depends(get_connection, scope="function"),
):
    """Return the complete dashboard using one database-pool checkout."""
    privilege_rows = connection.execute(
        """SELECT code FROM privileges
            WHERE user_has_global_privilege(current_user_id(), code)"""
    ).fetchall()
    privileges = {row["code"] for row in privilege_rows}

    overview_counts = {
        "aggregations": connection.execute(
            "SELECT count(*) AS total FROM authorized_aggregations_for_search"
        ).fetchone()["total"],
        "records": connection.execute(
            "SELECT count(*) AS total FROM authorized_records_for_search"
        ).fetchone()["total"],
    }
    for resource, privilege in (
        ("classification-schemes", "classifications.administer"),
        ("classifications", "classifications.administer"),
        ("org-units", "organization.administer"),
        ("roles", "organization.administer"),
        ("users", "identity.users.administer"),
    ):
        if privilege in privileges:
            table = resource.replace("-", "_")
            overview_counts[resource] = connection.execute(
                f'SELECT count(*) AS total FROM "{table}"'
            ).fetchone()["total"]

    classification_metrics = {
        "published_scheme_count": 0,
        "draft_scheme_count": 0,
        "inactive_scheme_count": 0,
        "branch_count": 0,
        "terminal_count": 0,
        "assignable_terminal_count": 0,
        "draft_terminal_count": 0,
        "inactive_classification_count": 0,
    }
    if "classifications.administer" in privileges:
        classification_metrics = dict(connection.execute(
            """WITH scheme_metrics AS (
                   SELECT scheme.id,
                          scheme.date_deactivated IS NOT NULL AS inactive,
                          scheme.date_deactivated IS NULL
                            AND (scheme.date_published IS NULL
                                 OR scheme.date_published > CURRENT_TIMESTAMP) AS draft,
                          scheme.date_deactivated IS NULL
                            AND scheme.date_published IS NOT NULL
                            AND scheme.date_published <= CURRENT_TIMESTAMP AS published,
                          count(classification.id) FILTER (
                              WHERE classification.id IS NOT NULL
                                AND NOT classification.is_terminal
                          ) AS branches,
                          count(classification.id) FILTER (
                              WHERE classification.is_terminal
                          ) AS terminals,
                          count(classification.id) FILTER (
                              WHERE classification.is_terminal
                                AND classification_scheme_is_eligible(scheme.id)
                                AND classification_is_effectively_active(classification.id)
                                AND EXISTS (
                                    SELECT 1 FROM effective_classification_retention_rule(classification.id)
                                )
                          ) AS assignable_terminals
                     FROM classification_schemes scheme
                LEFT JOIN classifications classification
                       ON classification.classification_scheme_id=scheme.id
                 GROUP BY scheme.id
               )
               SELECT count(*) FILTER (WHERE published) AS published_scheme_count,
                      count(*) FILTER (WHERE draft) AS draft_scheme_count,
                      count(*) FILTER (WHERE inactive) AS inactive_scheme_count,
                      coalesce(sum(branches),0) AS branch_count,
                      coalesce(sum(terminals),0) AS terminal_count,
                      coalesce(sum(assignable_terminals),0) AS assignable_terminal_count,
                      coalesce(sum(terminals) FILTER (WHERE draft),0) AS draft_terminal_count,
                      (SELECT count(*) FROM classifications
                        WHERE date_deactivated IS NOT NULL) AS inactive_classification_count
                 FROM scheme_metrics"""
        ).fetchone())

    unclassified_root_count = connection.execute(
        """SELECT count(*) AS total FROM authorized_aggregations_for_search
            WHERE parent_aggregation_id IS NULL AND classification_id IS NULL"""
    ).fetchone()["total"]

    ownership_counts = list(connection.execute(
        """WITH eligible_units AS (
               SELECT DISTINCT unit.id,unit.code,unit.name
               FROM user_role_assignments assignment
               JOIN roles role ON role.id=assignment.role_id
               JOIN org_units unit ON unit.id=role.org_unit_id
               WHERE assignment.user_id=current_user_id()
                 AND CURRENT_TIMESTAMP>=assignment.valid_from
                 AND (assignment.valid_until IS NULL OR CURRENT_TIMESTAMP<=assignment.valid_until)
                 AND role_effectively_active(role.id)
           )
           SELECT unit.id AS org_unit_id,unit.code AS org_unit_code,
                  unit.name AS org_unit_name,
                  (SELECT count(*) FROM aggregations aggregation
                    WHERE aggregation.owning_org_unit_id=unit.id
                      AND current_user_can_view_aggregation(aggregation.id)) AS aggregation_count,
                  (SELECT count(*) FROM records record
                    WHERE record.owning_org_unit_id=unit.id
                      AND current_user_can_view_record(record.id)) AS record_count
             FROM eligible_units unit
            ORDER BY unit.name COLLATE "C",unit.id"""
    ).fetchall())

    favourite_aggregations = list(connection.execute(
        """SELECT aggregation.id,aggregation.aggregation_number,aggregation.title,
                  CASE WHEN aggregation.parent_aggregation_id IS NULL
                            OR current_user_can_view_aggregation(aggregation.parent_aggregation_id)
                       THEN aggregation.parent_aggregation_id END AS parent_aggregation_id,
                  favourite.date_created AS date_favourited
             FROM user_favourite_aggregations favourite
             JOIN aggregations aggregation ON aggregation.id=favourite.aggregation_id
            WHERE favourite.user_id=%s
              AND current_user_can_view_aggregation(aggregation.id)
            ORDER BY favourite.date_created DESC,aggregation.id DESC""",
        (principal.user_id,),
    ).fetchall())
    favourite_records = list(connection.execute(
        """SELECT record.id,record.record_number,record.title,
                  CASE WHEN current_user_can_view_aggregation(record.aggregation_id)
                       THEN record.aggregation_id END AS aggregation_id,
                  CASE WHEN current_user_can_view_aggregation(record.aggregation_id)
                       THEN aggregation.aggregation_number END AS aggregation_number,
                  CASE WHEN current_user_can_view_aggregation(record.aggregation_id)
                       THEN aggregation.title END AS aggregation_title,
                  favourite.date_created AS date_favourited
             FROM user_favourite_records favourite
             JOIN records record ON record.id=favourite.record_id
             JOIN aggregations aggregation ON aggregation.id=record.aggregation_id
            WHERE favourite.user_id=%s AND current_user_can_view_record(record.id)
            ORDER BY favourite.date_created DESC,record.id DESC""",
        (principal.user_id,),
    ).fetchall())

    recent_activity = list(connection.execute(
        """WITH matching_events AS (
               SELECT event.entity_type,event.entity_id,event.operation,event.occurred_at,
                      row_number() OVER (
                          PARTITION BY event.entity_type,event.operation
                          ORDER BY event.occurred_at DESC,event.id DESC
                      ) AS position
                 FROM event_history event
                WHERE event.actor_user_id=%s
                  AND event.entity_type IN ('aggregation','record')
                  AND event.operation IN ('CREATE','UPDATE')
                  AND (%s::timestamptz IS NULL OR event.occurred_at >= %s)
           )
           SELECT event.entity_type,event.entity_id,event.operation,event.occurred_at,
                  coalesce(aggregation.title,record.title) AS title,
                  aggregation.aggregation_number,record.record_number
             FROM matching_events event
        LEFT JOIN aggregations aggregation
               ON event.entity_type='aggregation' AND aggregation.id=event.entity_id
              AND current_user_can_view_aggregation(aggregation.id)
        LEFT JOIN records record
               ON event.entity_type='record' AND record.id=event.entity_id
              AND current_user_can_view_record(record.id)
            WHERE event.position<=%s
              AND (aggregation.id IS NOT NULL OR record.id IS NOT NULL)
            ORDER BY event.occurred_at DESC,event.entity_type,event.entity_id""",
        (principal.user_id, recent_since, recent_since, recent_limit),
    ).fetchall())

    return {
        "overview_counts": overview_counts,
        "classification_metrics": classification_metrics,
        "unclassified_root_count": unclassified_root_count,
        "ownership_counts": ownership_counts,
        "favourites": {
            "aggregations": favourite_aggregations,
            "records": favourite_records,
        },
        "recent_activity": recent_activity,
    }
