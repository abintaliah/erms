import os

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb


def test_entity_translation_patch_merges_locales_and_uses_entity_version(client):
    user = client.get("/api/v1/users/1").json()
    saved = client.patch(
        "/api/v1/entity-translations/users/1/ar",
        json={"name": "مدير الاختبار", "description": "حساب إداري"},
        headers={"If-Match": str(user["version"]), "X-Change-Reason": "Add Arabic user metadata"},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["fields"] == {"name": "مدير الاختبار", "description": "حساب إداري"}
    assert body["canonical"]["name"] == "Test Administrator"
    assert body["version"] == user["version"] + 1

    stale = client.patch(
        "/api/v1/entity-translations/users/1/ar",
        json={"name": "قديم"},
        headers={"If-Match": str(user["version"]), "X-Change-Reason": "Competing edit"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_version"

    updated = client.patch(
        "/api/v1/entity-translations/users/1/ar",
        json={"description": "وصف محدث"},
        headers={"If-Match": str(body["version"]), "X-Change-Reason": "Refine Arabic description"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["fields"] == {
        "name": "مدير الاختبار", "description": "وصف محدث",
    }
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        translations = connection.execute(
            "SELECT translations FROM users WHERE id=1"
        ).fetchone()[0]
        assert translations == {"ar": updated.json()["fields"]}
        event = connection.execute(
            """SELECT changed_fields,reason FROM event_history
                 WHERE entity_type='user' AND entity_id=1 AND operation='UPDATE'
                 ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        assert "translations" in event[0]
        assert event[1] == "Refine Arabic description"


def test_entity_translation_validation_and_explicit_field_removal(client):
    scheme = client.get("/api/v1/classification-schemes/1").json()
    wrong_field = client.patch(
        "/api/v1/entity-translations/classification-schemes/1/ar",
        json={"name": "اسم"},
        headers={"If-Match": str(scheme["version"]), "X-Change-Reason": "Wrong field"},
    )
    assert wrong_field.status_code == 422
    assert wrong_field.json()["detail"]["code"] == "invalid_translation_field"

    blank = client.patch(
        "/api/v1/entity-translations/classification-schemes/1/ar",
        json={"title": "   "},
        headers={"If-Match": str(scheme["version"]), "X-Change-Reason": "Blank value"},
    )
    assert blank.status_code == 422
    assert blank.json()["detail"]["code"] == "blank_translation"

    saved = client.patch(
        "/api/v1/entity-translations/classification-schemes/1/ar",
        json={"title": "خطة الاختبار"},
        headers={"If-Match": str(scheme["version"]), "X-Change-Reason": "Add title"},
    ).json()
    removed = client.patch(
        "/api/v1/entity-translations/classification-schemes/1/ar",
        json={"title": None},
        headers={"If-Match": str(saved["version"]), "X-Change-Reason": "Remove title"},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["fields"] == {"title": None, "description": None}
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        assert connection.execute(
            "SELECT translations IS NULL FROM classification_schemes WHERE id=1"
        ).fetchone()[0] is True


def test_entity_translation_rejects_disabled_or_unknown_language(client):
    user = client.get("/api/v1/users/1").json()
    response = client.patch(
        "/api/v1/entity-translations/users/1/fr",
        json={"name": "Administrateur"},
        headers={"If-Match": str(user["version"]), "X-Change-Reason": "Unsupported language"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsupported_language"


def test_profile_translation_is_localized_in_profile_reads_and_references(client):
    profile = next(
        item for item in client.get("/api/v1/profiles?limit=500").json()
        if item["code"] == "ALL_PRIVS"
    )
    saved = client.patch(
        f"/api/v1/entity-translations/profiles/{profile['id']}/ar",
        json={"name": "جميع الصلاحيات", "description": "ملف الصلاحيات الشامل"},
        headers={
            "If-Match": str(profile["version"]),
            "X-Change-Reason": "Add Arabic profile metadata",
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["fields"]["name"] == "جميع الصلاحيات"

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            """INSERT INTO user_preferences(user_id,language_tag,working_timezone)
               VALUES (1,'ar','Asia/Dubai')
               ON CONFLICT (user_id) DO UPDATE SET language_tag=EXCLUDED.language_tag"""
        )

    detail = client.get(f"/api/v1/profiles/{profile['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["localized"]["name"] == "جميع الصلاحيات"
    references = client.get("/api/v1/profiles/reference?limit=500")
    assert references.status_code == 200, references.text
    localized = next(item for item in references.json() if item["id"] == profile["id"])
    assert localized["localized"]["description"] == "ملف الصلاحيات الشامل"


def test_builtin_role_canonical_metadata_is_immutable_but_translations_are_editable(client):
    roles = client.get("/api/v1/roles?include_system=true&limit=500")
    assert roles.status_code == 200, roles.text
    role = next(
        item for item in roles.json()
        if item["code"] == "text-indexer-service"
    )

    canonical_change = client.patch(
        f"/api/v1/roles/{role['id']}",
        json={"name": "Changed service role"},
        headers={"If-Match": str(role["version"])},
    )
    assert canonical_change.status_code == 409
    assert canonical_change.json()["detail"] == "built-in roles are read-only"

    translation_change = client.patch(
        f"/api/v1/entity-translations/roles/{role['id']}/ar",
        json={
            "name": "خدمة فهرسة النصوص",
            "description": "دور خدمة مدمج تديره المنصة",
        },
        headers={
            "If-Match": str(role["version"]),
            "X-Change-Reason": "Add Arabic metadata for protected service role",
        },
    )
    assert translation_change.status_code == 200, translation_change.text
    assert translation_change.json()["canonical"]["name"] == "Text Indexer Service"
    assert translation_change.json()["fields"]["name"] == "خدمة فهرسة النصوص"


def test_text_indexer_profile_is_translation_only(client):
    profiles = client.get("/api/v1/profiles?limit=500")
    assert profiles.status_code == 200, profiles.text
    profile = next(
        item for item in profiles.json()
        if item["code"] == "TEXT_INDEXER_SERVICE"
    )

    canonical_change = client.patch(
        f"/api/v1/profiles/{profile['id']}",
        json={"name": "Changed indexer profile"},
        headers={
            "If-Match": str(profile["version"]),
            "X-Change-Reason": "Attempt protected canonical update",
        },
    )
    assert canonical_change.status_code == 409
    assert canonical_change.json()["detail"] == "TEXT_INDEXER_SERVICE profile is protected"

    translation_change = client.patch(
        f"/api/v1/entity-translations/profiles/{profile['id']}/ar",
        json={
            "name": "ملف خدمة فهرسة النصوص",
            "description": "ملف مدمج لخدمة فهرسة النصوص الداخلية",
        },
        headers={
            "If-Match": str(profile["version"]),
            "X-Change-Reason": "Add Arabic metadata for protected service profile",
        },
    )
    assert translation_change.status_code == 200, translation_change.text
    assert translation_change.json()["canonical"]["name"] == "Text Indexer Service"
    assert translation_change.json()["fields"]["name"] == "ملف خدمة فهرسة النصوص"


def test_translated_search_uses_only_enabled_languages_and_indexed_prefilter(client):
    user = client.get("/api/v1/users/1").json()
    saved = client.patch(
        "/api/v1/entity-translations/users/1/ar",
        json={"name": "مدير الفهرسة"},
        headers={"If-Match": str(user["version"]), "X-Change-Reason": "Add searchable Arabic name"},
    )
    assert saved.status_code == 200, saved.text

    payload = {"where": {"field": "name", "operator": "contains_ci", "value": "الفهرسة"}}
    enabled = client.post("/api/v1/users/search", json=payload)
    assert enabled.status_code == 200, enabled.text
    assert [item["id"] for item in enabled.json()["items"]] == [1]

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute("SELECT set_config('app.change_reason','Phase 5 disabled-locale search test',true)")
        connection.execute("UPDATE supported_languages SET is_enabled=false WHERE language_tag='ar'")
    disabled = client.post("/api/v1/users/search", json=payload)
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["items"] == []

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute("SELECT set_config('app.change_reason','Restore Arabic after Phase 5 test',true)")
        connection.execute("UPDATE supported_languages SET is_enabled=true WHERE language_tag='ar'")
        connection.execute("SET enable_seqscan=off")
        plan = "\n".join(
            row[0] for row in connection.execute(
                "EXPLAIN (COSTS OFF) SELECT id FROM users WHERE translations::text ILIKE '%الفهرسة%'"
            ).fetchall()
        )
    assert "users_translation_text_trgm_idx" in plan


def test_paginated_administration_searches_return_preferred_language_projection(client):
    resources = (
        ("org-units", "name", "وحدة الاختبار المترجمة"),
        ("users", "name", "مستخدم الاختبار المترجم"),
        ("roles", "name", "دور الاختبار المترجم"),
        ("classification-schemes", "title", "خطة الاختبار المترجمة"),
        ("classifications", "title", "تصنيف الاختبار المترجم"),
    )
    identifiers: dict[str, int] = {}
    for resource, field, translated_value in resources:
        current = client.get(f"/api/v1/{resource}/1")
        assert current.status_code == 200, current.text
        identifiers[resource] = current.json()["id"]
        saved = client.patch(
            f"/api/v1/entity-translations/{resource}/{identifiers[resource]}/ar",
            json={field: translated_value},
            headers={
                "If-Match": str(current.json()["version"]),
                "X-Change-Reason": "Verify localized administration paging",
            },
        )
        assert saved.status_code == 200, saved.text

    preference = client.get("/api/v1/preferences").json()
    selected = client.put(
        "/api/v1/preferences",
        headers={"If-Match": str(preference["version"])},
        json={"language_tag": "ar", "working_timezone": "Asia/Dubai"},
    )
    assert selected.status_code == 200, selected.text

    for resource, field, translated_value in resources:
        response = client.post(
            f"/api/v1/{resource}/search",
            params={"include_system": "true"} if resource == "roles" else None,
            json={"limit": 50, "offset": 0},
        )
        assert response.status_code == 200, response.text
        item = next(
            row for row in response.json()["items"]
            if row["id"] == identifiers[resource]
        )
        assert item["localized"][field] == translated_value


def test_paginated_identity_searches_sort_by_displayed_preferred_language_name(client):
    preference = client.get("/api/v1/preferences").json()
    selected = client.put(
        "/api/v1/preferences",
        headers={"If-Match": str(preference["version"])},
        json={"language_tag": "ar", "working_timezone": "Asia/Dubai"},
    )
    assert selected.status_code == 200, selected.text

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        root_id = connection.execute(
            "SELECT id FROM org_units ORDER BY id LIMIT 1"
        ).fetchone()[0]
        rows = {
            "org-units": (
                connection.execute(
                    """INSERT INTO org_units(code,name,translations)
                       VALUES ('alpha-unit','Alpha Unit',%s),('zulu-unit','Zulu Unit',%s)
                       RETURNING id,name""",
                    (Jsonb({"ar": {"name": "وحدة الياء"}}), Jsonb({"ar": {"name": "الوحدة الأولى"}})),
                ).fetchall()
            ),
            "users": (
                connection.execute(
                    """INSERT INTO users(name,email,translations)
                       VALUES ('Alpha User','alpha-sort@test.invalid',%s),
                              ('Zulu User','zulu-sort@test.invalid',%s)
                       RETURNING id,name""",
                    (Jsonb({"ar": {"name": "مستخدم الياء"}}), Jsonb({"ar": {"name": "المستخدم الأول"}})),
                ).fetchall()
            ),
            "roles": (
                connection.execute(
                    """INSERT INTO roles(org_unit_id,code,name,translations)
                       VALUES (%s,'alpha-role','Alpha Role',%s),
                              (%s,'zulu-role','Zulu Role',%s)
                       RETURNING id,name""",
                    (root_id, Jsonb({"ar": {"name": "دور الياء"}}), root_id, Jsonb({"ar": {"name": "الدور الأول"}})),
                ).fetchall()
            ),
        }

    for resource, inserted in rows.items():
        response = client.post(
            f"/api/v1/{resource}/search",
            params={"include_system": "true"} if resource == "roles" else None,
            json={
                "where": {
                    "field": "id", "operator": "in",
                    "value": [row[0] for row in inserted],
                },
                "sort": [{"field": "name", "direction": "asc"}],
                "limit": 1, "offset": 0,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 2
        assert response.json()["items"][0]["name"].startswith("Zulu")
        assert response.json()["items"][0]["localized"]["name"].startswith("ال")


@pytest.mark.parametrize(('resource', 'table', 'entity_type', 'primary'), [
    ('roles', 'roles', 'role', 'name'),
    ('users', 'users', 'user', 'name'),
    ('org-units', 'org_units', 'org_unit', 'name'),
    ('profiles', 'profiles', 'profile', 'name'),
    ('security-levels', 'security_levels', 'security_level', 'name'),
    ('classifications', 'classifications', 'classification', 'title'),
    ('classification-schemes', 'classification_schemes', 'classification_scheme', 'title'),
])
def test_entity_translation_audit_preserves_before_after_for_all_entities(client, resource, table, entity_type, primary):
    with psycopg.connect(os.environ['DATABASE_URL']) as connection:
        entity_id, previous = connection.execute(sql.SQL(
            'SELECT id, translations FROM {} ORDER BY id LIMIT 1'
        ).format(sql.Identifier(table))).fetchone()
    path = f'/api/v1/entity-translations/{resource}/{entity_id}/ar'
    current = client.get(path)
    assert current.status_code == 200, current.text
    version = current.json()['version']
    for phase, values in [
        ('add', {primary: 'الاسم التجريبي الأول', 'description': 'الوصف التجريبي الأول'}),
        ('edit', {primary: 'الاسم التجريبي المعدل', 'description': 'الوصف التجريبي المعدل'}),
        ('remove', {primary: None, 'description': None}),
    ]:
        reason = f'Audit verification: {resource} {phase}'
        response = client.patch(path, json=values, headers={
            'If-Match': str(version), 'X-Change-Reason': reason,
            'X-Event-Source': 'web_ui',
        })
        assert response.status_code == 200, response.text
        version = response.json()['version']
        expected = dict(previous or {})
        if phase == 'remove':
            expected.pop('ar', None)
        else:
            expected['ar'] = values
        expected = expected or None
        with psycopg.connect(os.environ['DATABASE_URL']) as connection:
            row = connection.execute(
                '''SELECT id,before_state,after_state,changed_fields,reason,source
                   FROM event_history WHERE entity_type=%s AND entity_id=%s AND operation='UPDATE'
                   ORDER BY id DESC LIMIT 1''', (entity_type, entity_id),
            ).fetchone()
        assert row is not None
        event_id, before, after, changed, saved_reason, source = row
        assert before['translations'] == previous
        assert after['translations'] == expected
        assert 'translations' in changed
        assert saved_reason == reason
        assert source == 'web_ui'
        # Verify the API used by history screens retains the same snapshots.
        events = client.get('/api/v1/event-history', params={
            'entity_type': entity_type, 'entity_id': entity_id, 'operation': 'UPDATE',
        })
        assert events.status_code == 200, events.text
        event = next(item for item in events.json() if item['id'] == event_id)
        assert event['before_state']['translations'] == previous
        assert event['after_state']['translations'] == expected
        assert 'translations' in event['changed_fields']
        print(f'{resource}: {phase}: database and API snapshots preserved (event {event_id})')
        previous = expected
