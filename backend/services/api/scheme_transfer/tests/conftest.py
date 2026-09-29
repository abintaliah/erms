import copy
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
import pytest
from fastapi.testclient import TestClient

# Refuse collection through an accidental persistent DATABASE_URL before app import.
if os.environ.get("TRANSFER_DISPOSABLE_RUN") != "1":
    raise RuntimeError(
        "Run tools/test_scheme_transfer.py to provision disposable databases"
    )
for key in ("DATABASE_URL", "TRANSFER_SOURCE_DATABASE_URL"):
    if not psycopg.conninfo.conninfo_to_dict(os.environ[key])["dbname"].startswith(
        "erms_transfer_test_"
    ):
        raise RuntimeError("Disposable database isolation check failed")

from backend.services.api.main import app
from backend.services.api.authentication import hash_password
from backend.services.api.scheme_transfer.codec import seal


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as client:
        with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as c:
            c.execute("SELECT set_config('app.event_source','seeding',true)")
            org = c.execute(
                "INSERT INTO org_units(code,name) VALUES ('test-root','Test Root') RETURNING id"
            ).fetchone()["id"]
            uid = c.execute(
                "INSERT INTO users(name,email) VALUES ('Transfer Administrator','transfer@test.invalid') RETURNING id"
            ).fetchone()["id"]
            role = c.execute(
                "INSERT INTO roles(org_unit_id,code,name,is_information_governance) VALUES (%s,'transfer-admin','Transfer Administrator',true) RETURNING id",
                (org,),
            ).fetchone()["id"]
            c.execute(
                "INSERT INTO user_role_assignments(user_id,role_id) VALUES (%s,%s)",
                (uid, role),
            )
            c.execute(
                "INSERT INTO user_credentials(user_id,password_hash,must_change_password) VALUES (%s,%s,false)",
                (uid, hash_password("Temporary-Test-Password-123!")),
            )
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "transfer@test.invalid",
                "password": "Temporary-Test-Password-123!",
            },
        )
        assert response.status_code == 200, response.text
        client.headers["X-CSRF-Token"] = client.cookies.get("erms_csrf")
        # Install an additional language through the supported administration API.
        response = client.post(
            "/api/v1/admin/i18n/languages",
            json=dict(
                language_tag="fr",
                english_name="French",
                native_name="Français",
                direction="ltr",
                is_enabled=True,
                is_default=False,
                formatting_config={"locale": "fr"},
            ),
            headers={"X-Change-Reason": "Install disposable acceptance language"},
        )
        assert response.status_code == 201, response.text
        from backend.services.api.localization import (
            synchronize_generated_arabic_drafts,
        )

        synchronize_generated_arabic_drafts()
        # Publish valid imported test translations through the normal publication
        # service. Arabic starts from the maintained artifact; French uses explicit
        # test translations, never source_copy masquerading as published wording.
        with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as c:
            c.execute("SELECT set_config('app.event_source','seeding',true)")
            c.execute(
                "SELECT set_config('app.change_reason','Seed disposable test language',true)"
            )
            c.execute(
                "UPDATE ui_message_translations SET translated_text='FR ' || translated_text,origin='imported' WHERE language_tag='fr'"
            )
        for lang in ("ar", "fr"):
            with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as c:
                items = c.execute(
                    "SELECT message_key,version FROM ui_message_translations WHERE language_tag=%s AND origin<>'source_copy'",
                    (lang,),
                ).fetchall()
            response = client.post(
                f"/api/v1/admin/i18n/translations/{lang}/bulk-review-publish",
                json={"items": items},
                headers={"X-Change-Reason": "Publish disposable acceptance catalogue"},
            )
            assert response.status_code == 200, response.text
        with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as c:
            for lang in ("ar", "fr"):
                counts = c.execute(
                    """SELECT count(*) AS missing FROM ui_message_definitions d LEFT JOIN ui_message_translations t ON t.message_key=d.message_key AND t.language_tag=%s WHERE NOT d.is_deprecated AND (t.published_text IS NULL OR t.needs_review)""",
                    (lang,),
                ).fetchone()
                assert counts["missing"] == 0
        yield client


@pytest.fixture
def connection(client):
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as c:
        yield c


@pytest.fixture
def package():
    from uuid import uuid4

    d = "2026-01-01T08:00:00.000000Z"
    common = dict(
        title="Administrative records",
        description='Arabic العربية, newline\n"quote"',
        authority=None,
        scope_note="",
        date_created=d,
        date_updated=d,
        date_deactivated=None,
        date_first_used=None,
        version="9007199254740993",
        translations={
            "ar": {"title": "السجلات الإدارية"},
            "fr": {"title": "Documents administratifs"},
        },
    )
    rule = dict(
        source_id="200",
        current_period_years=2,
        intermediate_period_years=5,
        final_disposition="destruction",
        instructions=None,
        date_created=d,
        date_updated=d,
        version="1",
    )
    classes = [
        dict(
            common,
            source_id="100",
            code="01",
            parent_code=None,
            keywords=None,
            is_terminal=False,
            retention_rule=rule,
        ),
        dict(
            common,
            source_id="101",
            code="01.01",
            parent_code="01",
            keywords="",
            is_terminal=True,
            retention_rule=None,
        ),
    ]
    scheme = dict(
        common,
        source_id="12",
        code="T-" + uuid4().hex[:10],
        edition="2026",
        date_published=d,
        classifications=classes,
    )
    return seal(
        dict(
            package_type="classification_scheme_export",
            format_version="1.0",
            manifest=dict(
                export_id=str(uuid4()),
                exported_at=d,
                exported_by=dict(
                    source_user_id="42",
                    username="source@test.invalid",
                    display_name="Source User",
                ),
                source=dict(
                    application="Wathiq",
                    application_revision="a" * 40,
                    database_name="source",
                    schema_version="fixture",
                ),
                counts=dict(classifications=2, retention_rules=1),
            ),
            data={"scheme": scheme},
        )
    )
