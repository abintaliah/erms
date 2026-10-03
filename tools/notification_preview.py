"""Test-only producer assembly and seed for a disposable browser preview."""

import os
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from backend.services.api.messaging import notification_registry as contracts


def definitions():
    return (
        contracts.SystemNotificationDefinition(
            producer_code="preview.review",
            feature_code="preview",
            event_type="reviewed",
            contract_version=1,
            required_for_business_commit=False,
            placeholders={
                "name": contracts.Placeholder(type="text", max_length=80),
                "day": contracts.Placeholder(type="date"),
            },
            sample_context={"name": "Example recipient", "day": "2026-10-03"},
        ),
    )


def assert_disposable():
    assert psycopg.conninfo.conninfo_to_dict(os.environ["DATABASE_URL"])[
        "dbname"
    ].startswith("erms_messaging_test_")


def seed():
    assert_disposable()
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as c:
        c.execute("SELECT set_config('app.event_source','seeding',true)")
        for definition in definitions():
            c.execute(
                "INSERT INTO system_notification_producers(producer_code,feature_code,event_type,contract_version,required_for_business_commit,contract_definition) VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    definition.producer_code,
                    definition.feature_code,
                    definition.event_type,
                    definition.contract_version,
                    definition.required_for_business_commit,
                    Jsonb(definition.contract()),
                ),
            )


if __name__ == "__main__":
    seed()
else:
    assert_disposable()
    # Explicit test application assembly. The production registry stays empty.
    contracts.application_definitions = definitions
    from backend.services.api.main import app
