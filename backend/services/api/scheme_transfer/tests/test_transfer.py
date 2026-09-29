import copy
import csv
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from zipfile import ZipFile

import psycopg
from psycopg.rows import dict_row
import pytest

from backend.services.api.scheme_transfer.codec import (
    TransferError,
    decode,
    encode,
    seal,
)
from backend.services.api.scheme_transfer.service import export_package, import_package


def upload(client, package, kind="json"):
    return client.post(
        "/api/v1/classification-schemes/import",
        params={"format": kind},
        files={
            "file": (
                "scheme." + kind,
                encode(package, kind),
                "application/octet-stream",
            )
        },
    )


@pytest.mark.parametrize("kind", ["json", "csv"])
def test_roundtrip_and_provenance(client, connection, package, kind):
    response = upload(client, package, kind)
    assert response.status_code == 201, response.text
    sid = response.json()["id"]
    row = connection.execute(
        "SELECT * FROM classification_schemes WHERE id=%s", (sid,)
    ).fetchone()
    assert row["date_published"] is None
    assert row["translations"] == package["data"]["scheme"]["translations"]
    assert row["version"] == 9007199254740993
    history = connection.execute(
        "SELECT * FROM event_history WHERE entity_type='classification_scheme' AND entity_id=%s AND operation='CREATE'",
        (sid,),
    ).fetchone()
    assert history["actor_user_id"] != 42
    assert (
        history["metadata"]["classification_scheme_import"]["source_entity"][
            "date_published"
        ]
        == package["data"]["scheme"]["date_published"]
    )
    for fmt in ("json", "csv"):
        exported = client.get(
            f"/api/v1/classification-schemes/{sid}/export", params={"format": fmt}
        )
        assert exported.status_code == 200, exported.text
        result = decode(exported.content, fmt)
        original = copy.deepcopy(package["data"]["scheme"])
        actual = result["data"]["scheme"]
        original["date_published"] = None

        def scrub(x):
            if isinstance(x, dict):
                return {k: scrub(v) for k, v in x.items() if k != "source_id"}
            if isinstance(x, list):
                return [scrub(v) for v in x]
            return x

        assert scrub(actual) == scrub(original)
    before = connection.execute("SELECT count(*) AS n FROM event_history").fetchone()[
        "n"
    ]
    for fmt in ("json", "csv"):
        duplicate = upload(client, package, fmt)
        assert duplicate.status_code == 409, duplicate.text
    assert (
        connection.execute("SELECT count(*) AS n FROM event_history").fetchone()["n"]
        == before
    )


@pytest.mark.parametrize("kind", ["json", "csv"])
def test_codec_values_and_reordering(package, kind):
    raw = encode(package, kind)
    assert decode(raw, kind) == package
    if kind == "json":
        raw = json.dumps(package, sort_keys=True, ensure_ascii=True).encode()
    else:
        rows = list(csv.reader(io.StringIO(raw.decode())))
        out = io.StringIO(newline="")
        w = csv.writer(out, lineterminator="\n")
        w.writerow(rows[0])
        w.writerows(reversed(rows[1:]))
        raw = b"\xef\xbb\xbf" + out.getvalue().encode()
    assert decode(raw, kind) == package


@pytest.mark.parametrize("kind", ["json", "csv"])
def test_checksum_failure_no_writes(client, connection, package, kind):
    raw = encode(package, kind).replace(b"Administrative records", b"Tampered records")
    before = connection.execute(
        "SELECT count(*) AS n FROM classification_schemes"
    ).fetchone()["n"]
    response = client.post(
        "/api/v1/classification-schemes/import",
        params={"format": kind},
        files={"file": ("x." + kind, raw)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"].endswith("checksum_mismatch")
    assert (
        connection.execute(
            "SELECT count(*) AS n FROM classification_schemes"
        ).fetchone()["n"]
        == before
    )


@pytest.mark.parametrize("kind", ["json", "csv"])
def test_unsupported_language(client, connection, package, kind):
    package["data"]["scheme"]["translations"]["zz"] = {"title": "Unsupported"}
    seal(package)
    response = upload(client, package, kind)
    assert response.status_code == 422, response.text
    assert (
        connection.execute(
            "SELECT 1 FROM classification_schemes WHERE code=%s",
            (package["data"]["scheme"]["code"],),
        ).fetchone()
        is None
    )


def test_concurrent_duplicate(client, package):
    def run(kind):
        try:
            with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as c:
                import_package(c, decode(encode(package, kind), kind))
            return True
        except (TransferError, psycopg.IntegrityError):
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(run, ("json", "csv"))) == [False, True]


def test_late_failure_rolls_back(client, package):
    # Force a failure after all entity and provenance writes have occurred.
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as c:
        with pytest.raises(RuntimeError):
            with c.transaction():
                import_package(c, package)
                raise RuntimeError("late failure")
        assert (
            c.execute(
                "SELECT 1 FROM classification_schemes WHERE code=%s",
                (package["data"]["scheme"]["code"],),
            ).fetchone()
            is None
        )
        assert (
            c.execute(
                "SELECT 1 FROM event_history WHERE metadata->'classification_scheme_import'->>'source_scheme_code'=%s",
                (package["data"]["scheme"]["code"],),
            ).fetchone()
            is None
        )


@pytest.mark.parametrize(
    "language,direction", [("en", "ltr"), ("ar", "rtl"), ("fr", "ltr")]
)
def test_word_languages(client, package, language, direction):
    response = upload(client, package)
    assert response.status_code == 201, response.text
    response = client.get(
        f"/api/v1/classification-schemes/{response.json()['id']}/export",
        params={"format": "docx", "language": language},
    )
    assert response.status_code == 200, response.text
    from lxml import etree

    with ZipFile(io.BytesIO(response.content)) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        assert len(root.xpath("//w:tbl", namespaces=ns)) == 2
        assert root.xpath("//w:pgSz/@w:orient", namespaces=ns) == ["landscape"]
        assert root.xpath("//w:pgSz/@w:w", namespaces=ns) == ["19440"]
        assert root.xpath("//w:pgSz/@w:h", namespaces=ns) == ["12240"]
        assert len(root.xpath("//w:tblHeader", namespaces=ns)) == 2
        assert ("1" in root.xpath("//w:bidi/@w:val", namespaces=ns)) == (
            direction == "rtl"
        )
        styles = etree.fromstring(z.read("word/styles.xml"))
        for style_id in ("Normal", "Title", "Heading1", "Heading2"):
            style = styles.xpath(f'//w:style[@w:styleId="{style_id}"]', namespaces=ns)[
                0
            ]
            assert style.xpath("./w:rPr/w:rFonts/@w:ascii", namespaces=ns) == ["Changa"]
            assert style.xpath("./w:rPr/w:rFonts/@w:cs", namespaces=ns) == ["Changa"]
            assert style.xpath("./w:rPr/w:sz/@w:val", namespaces=ns) == ["20"]
            assert style.xpath("./w:rPr/w:szCs/@w:val", namespaces=ns) == ["20"]
        assert language in styles.xpath(
            '//w:style[@w:styleId="Normal"]//w:lang/@w:val', namespaces=ns
        )
        assert bool(
            root.xpath(
                "//w:bidiVisual[not(@w:val) or @w:val='1' or @w:val='true']",
                namespaces=ns,
            )
        ) == (direction == "rtl")
        assert any(
            int(value) > 0 for value in root.xpath("//w:ind/@w:start", namespaces=ns)
        )
        assert not root.xpath("//w:ind/@w:right | //w:ind/@w:left", namespaces=ns)
        shading = root.xpath("//w:shd/@w:fill", namespaces=ns)
        assert "E8EFF8" in shading and "EDF5F1" in shading
        table = root.xpath("//w:tbl", namespaces=ns)[1]
        assert len(table.xpath("./w:tr", namespaces=ns)) == 3
        widths = [
            int(v) for v in table.xpath("./w:tblGrid/w:gridCol/@w:w", namespaces=ns)
        ]
        assert len(widths) == 8
        assert widths[0] < widths[2] and widths[1] < widths[0]
        assert sum(widths) <= 19440 - 2 * 792
        for row in table.xpath("./w:tr", namespaces=ns):
            assert [
                int(v) for v in row.xpath("./w:tc/w:tcPr/w:tcW/@w:w", namespaces=ns)
            ] == widths
        for row in table.xpath("./w:tr", namespaces=ns)[1:]:
            cells = row.xpath("./w:tc", namespaces=ns)
            assert "".join(cells[3].itertext()) == "2"
            assert "".join(cells[4].itertext()) == "5"
            assert "".join(cells[5].itertext())
        text = "".join(root.itertext())
        assert not any(
            character in text
            for character in "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
        )
        assert "2026-01-01T08:00:00.000000Z" not in text
        assert "08:00 UTC" in text
        assert {"en": "January", "ar": "يناير", "fr": "janvier"}[language] in text
        assert root.xpath("//w:rPr/w:rtl[@w:val='0']", namespaces=ns)
        assert root.xpath(
            "//w:rPr/w:rtl[not(@w:val) or @w:val='1' or @w:val='true']",
            namespaces=ns,
        )
        assert "Documents administratifs" in "".join(root.itertext())
        if language == "ar":
            assert "الرمز" in "".join(root.itertext())
        if language == "fr":
            assert "FR " in "".join(root.itertext())
    output = os.environ.get("TRANSFER_QA_DIR")
    if output:
        from pathlib import Path

        Path(output).mkdir(parents=True, exist_ok=True)
        Path(output, f"scheme-{language}.docx").write_bytes(response.content)


@pytest.mark.parametrize("kind", ["json", "csv"])
def test_two_database_roundtrip(client, package, kind):
    with psycopg.connect(
        os.environ["TRANSFER_SOURCE_DATABASE_URL"], row_factory=dict_row
    ) as source:
        # Source language rows and source actor are fixture data, never copied into destination.
        source.execute("SELECT set_config('app.event_source','seeding',true)")
        source.execute(
            "SELECT set_config('app.change_reason','Install source fixture language',true)"
        )
        source.execute(
            "INSERT INTO supported_languages(language_tag,english_name,native_name,direction) VALUES ('fr','French','Français','ltr') ON CONFLICT DO NOTHING"
        )
        uid = source.execute(
            "INSERT INTO users(name,email) VALUES ('Exporter',%s) RETURNING id",
            (package["data"]["scheme"]["code"] + "@test.invalid",),
        ).fetchone()["id"]
        sid = import_package(source, package)["id"]
    with psycopg.connect(
        os.environ["TRANSFER_SOURCE_DATABASE_URL"], row_factory=dict_row
    ) as source:
        source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        exported = export_package(source, sid, uid)
    assert upload(client, exported, kind).status_code == 201


@pytest.mark.parametrize("kind", ["json", "csv"])
@pytest.mark.parametrize(
    "publication", [None, "2026-01-05T08:00:00.000000Z", "2099-01-05T08:00:00.000000Z"]
)
def test_draft_import(client, connection, package, kind, publication):
    package["data"]["scheme"]["date_published"] = publication
    seal(package)
    response = upload(client, package, kind)
    assert response.status_code == 201, response.text
    row = connection.execute(
        "SELECT date_published,classification_scheme_is_eligible(id) AS eligible FROM classification_schemes WHERE id=%s",
        (response.json()["id"],),
    ).fetchone()
    assert row == {"date_published": None, "eligible": False}


@pytest.mark.parametrize("kind", ["json", "csv"])
@pytest.mark.parametrize("translations", [None, {}, {"ar": {"description": "وصف فقط"}}])
def test_null_empty_and_missing_translation_fields(client, package, kind, translations):
    package["data"]["scheme"]["translations"] = translations
    for c in package["data"]["scheme"]["classifications"]:
        c["translations"] = translations
    seal(package)
    assert decode(encode(package, kind), kind) == package
    assert upload(client, package, kind).status_code == 201


@pytest.mark.parametrize("kind", ["json", "csv"])
@pytest.mark.parametrize(
    "translation_owner", ["scheme", "classifications", "both", "null", "empty"]
)
def test_only_administer_privilege(
    client, connection, package, kind, translation_owner
):
    scheme = package["data"]["scheme"]
    if translation_owner in ("classifications", "null", "empty"):
        scheme["translations"] = {} if translation_owner == "empty" else None
    if translation_owner in ("scheme", "null", "empty"):
        for item in scheme["classifications"]:
            item["translations"] = {} if translation_owner == "empty" else None
    seal(package)
    # Remove all unrelated privileges from the test role's profile inside a
    # committed fixture change; restore them even when the test fails.
    profile = connection.execute(
        "SELECT profile_id FROM roles WHERE code='transfer-admin'"
    ).fetchone()["profile_id"]
    grants = connection.execute(
        "SELECT privilege_id FROM profile_privileges WHERE profile_id=%s", (profile,)
    ).fetchall()
    connection.execute(
        "DELETE FROM profile_privileges WHERE profile_id=%s AND privilege_id<>(SELECT id FROM privileges WHERE code='classifications.administer')",
        (profile,),
    )
    connection.commit()
    try:
        response = upload(client, package, kind)
        assert response.status_code == 201, response.text
        sid = response.json()["id"]
        for fmt in ("json", "csv", "docx"):
            result = client.get(
                f"/api/v1/classification-schemes/{sid}/export",
                params={"format": fmt, "language": "ar"},
            )
            assert result.status_code == 200, result.text
        # No standalone metadata-editing permission is implied by import.
        denied = client.get(
            f"/api/v1/entity-translations/classification-schemes/{sid}/ar"
        )
        assert denied.status_code == 403, denied.text
        connection.execute(
            "DELETE FROM profile_privileges WHERE profile_id=%s", (profile,)
        )
        connection.commit()
        assert upload(client, package, kind).status_code == 403
        assert (
            client.get(
                f"/api/v1/classification-schemes/{sid}/export",
                params={"format": "json"},
            ).status_code
            == 403
        )
        connection.execute(
            "INSERT INTO profile_privileges(profile_id,privilege_id) SELECT %s,id FROM privileges WHERE code IN ('classification_scheme.modify_metadata','classification.modify_metadata')",
            (profile,),
        )
        connection.commit()
        assert upload(client, package, kind).status_code == 403
        assert (
            client.get(
                f"/api/v1/classification-schemes/{sid}/export", params={"format": "csv"}
            ).status_code
            == 403
        )
    finally:
        with psycopg.connect(os.environ["DATABASE_URL"]) as restore:
            for grant in grants:
                restore.execute(
                    "INSERT INTO profile_privileges(profile_id,privilege_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                    (profile, grant["privilege_id"]),
                )


@pytest.mark.parametrize("kind", ["json", "csv"])
@pytest.mark.parametrize(
    "bad",
    [
        "cycle",
        "missing_parent",
        "terminal_parent",
        "missing_rule",
        "duplicate_code",
        "invalid_date",
        "nul",
    ],
)
def test_invalid_domain_no_writes(client, connection, package, bad, kind):
    scheme = package["data"]["scheme"]
    root, child = scheme["classifications"]
    if bad == "cycle":
        root["parent_code"] = child["code"]
        child["is_terminal"] = False
    if bad == "missing_parent":
        child["parent_code"] = "absent"
    if bad == "terminal_parent":
        root["is_terminal"] = True
    if bad == "missing_rule":
        root["retention_rule"] = None
        package["manifest"]["counts"]["retention_rules"] = 0
    if bad == "duplicate_code":
        child["code"] = root["code"]
    if bad == "invalid_date":
        root["date_deactivated"] = "2025-01-01T00:00:00.000000Z"
    if bad == "nul":
        root["title"] = "invalid\x00text"
    from backend.services.api.scheme_transfer.codec import digest

    package["manifest"]["checksum"]["value"] = digest(package)
    raw = json.dumps(package).encode()
    if kind == "csv":
        from unittest.mock import patch
        from backend.services.api.scheme_transfer.codec import to_csv

        # Construct malformed input without the exporter's graph validation.
        with patch(
            "backend.services.api.scheme_transfer.codec.ordered", lambda items: items
        ):
            raw = to_csv(package)
    response = client.post(
        "/api/v1/classification-schemes/import",
        params={"format": kind},
        files={"file": ("x." + kind, raw)},
    )
    assert response.status_code == (
        409 if bad == "duplicate_code" and kind == "json" else 422
    ), response.text
    assert (
        connection.execute(
            "SELECT 1 FROM classification_schemes WHERE code=%s", (scheme["code"],)
        ).fetchone()
        is None
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_checksum",
        "wrong_algorithm",
        "duplicate_key",
        "unknown_property",
        "wrong_type",
        "nan",
        "trailing",
    ],
)
def test_invalid_json(package, mutation):
    if mutation == "missing_checksum":
        del package["manifest"]["checksum"]
    if mutation == "wrong_algorithm":
        package["manifest"]["checksum"]["algorithm"] = "MD5"
    if mutation == "unknown_property":
        package["extra"] = "x"
    if mutation == "wrong_type":
        package["data"]["scheme"]["version"] = 1
    raw = json.dumps(package).encode()
    if mutation == "duplicate_key":
        raw = raw.replace(
            b'"format_version": "1.0"',
            b'"format_version": "1.0", "format_version": "1.0"',
        )
    if mutation == "nan":
        raw = raw.replace(b'"classifications": 2', b'"classifications": NaN')
    if mutation == "trailing":
        raw += b"{}"
    with pytest.raises(TransferError):
        decode(raw, "json")


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_manifest",
        "duplicate_manifest",
        "bad_header",
        "row_width",
        "owner",
        "unknown_field",
        "orphan_translation",
        "wrong_type",
        "missing_field",
        "orphan_rule",
        "malformed_quote",
    ],
)
def test_invalid_csv(package, mutation):
    rows = list(csv.reader(io.StringIO(encode(package, "csv").decode())))
    if mutation == "missing_manifest":
        rows.pop(1)
    if mutation == "duplicate_manifest":
        rows.append(rows[1])
    if mutation == "bad_header":
        rows[0][0] = "version"
    if mutation == "row_width":
        rows[1].pop()
    if mutation == "owner":
        rows[1][3] = "unexpected"
    if mutation == "unknown_field":
        rows[1][6] = "unknown"
    if mutation == "wrong_type":
        next(row for row in rows if row[6] == "current_period_years")[8] = "2.0"
    if mutation == "missing_field":
        rows.remove(
            next(row for row in rows if row[1] == "scheme" and row[6] == "title")
        )
    if mutation == "orphan_rule":
        for row in rows:
            if row[1] == "retention_rule":
                row[3] = "absent"
    if mutation == "orphan_translation":
        rows.append(
            [
                "1.0",
                "translation",
                package["data"]["scheme"]["code"],
                "absent",
                "",
                "9",
                "title",
                "ar",
                "نص",
                "value",
            ]
        )
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    if mutation == "malformed_quote":
        out.write('"unterminated')
    with pytest.raises(TransferError):
        decode(out.getvalue().encode(), "csv")


def test_snapshot_and_no_source_mutation(client, connection, package):
    sid = upload(client, package).json()["id"]
    actor = connection.execute(
        "SELECT id FROM users WHERE email='transfer@test.invalid'"
    ).fetchone()["id"]
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as snap:
        snap.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        first = export_package(snap, sid, actor)
        with psycopg.connect(os.environ["DATABASE_URL"]) as writer:
            writer.execute(
                "UPDATE classification_schemes SET title='New title' WHERE id=%s",
                (sid,),
            )
        second = export_package(snap, sid, actor)
        assert second["data"] == first["data"]
    assert (
        connection.execute(
            "SELECT title FROM classification_schemes WHERE id=%s", (sid,)
        ).fetchone()["title"]
        == "New title"
    )


def test_case_variant_duplicate(client, package):
    assert upload(client, package).status_code == 201
    package["data"]["scheme"]["code"] = package["data"]["scheme"]["code"].swapcase()
    seal(package)
    assert upload(client, package, "csv").status_code == 409


def test_empty_and_deep(package):
    scheme = package["data"]["scheme"]
    scheme["classifications"] = []
    package["manifest"]["counts"] = dict(classifications=0, retention_rules=0)
    seal(package)
    assert decode(encode(package, "csv"), "csv") == package
    template = dict(
        source_id="1",
        code="x",
        parent_code=None,
        title="Deep",
        description=None,
        authority=None,
        scope_note=None,
        keywords=None,
        is_terminal=False,
        date_created=scheme["date_created"],
        date_updated=scheme["date_updated"],
        date_deactivated=None,
        date_first_used=None,
        version="1",
        translations=None,
        retention_rule=None,
    )
    scheme["classifications"] = [
        dict(
            template,
            source_id=str(i + 1),
            code=f"{i:04}",
            parent_code=f"{i-1:04}" if i else None,
        )
        for i in range(1100)
    ]
    package["manifest"]["counts"]["classifications"] = 1100
    seal(package)
    assert decode(encode(package, "csv"), "csv") == package


@pytest.mark.parametrize("kind", ["json", "csv"])
def test_disabled_language_is_atomic(client, connection, package, kind):
    connection.execute(
        "SELECT set_config('app.change_reason','Disposable compatibility test',true)"
    )
    connection.execute(
        "UPDATE supported_languages SET is_enabled=false WHERE language_tag='fr'"
    )
    connection.commit()
    try:
        response = upload(client, package, kind)
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"].endswith("unsupported_language")
        assert (
            connection.execute(
                "SELECT 1 FROM classification_schemes WHERE code=%s",
                (package["data"]["scheme"]["code"],),
            ).fetchone()
            is None
        )
        assert (
            connection.execute(
                "SELECT is_enabled FROM supported_languages WHERE language_tag='fr'"
            ).fetchone()["is_enabled"]
            is False
        )
    finally:
        with psycopg.connect(os.environ["DATABASE_URL"]) as restore:
            restore.execute(
                "SELECT set_config('app.change_reason','Restore disposable language',true)"
            )
            restore.execute(
                "UPDATE supported_languages SET is_enabled=true WHERE language_tag='fr'"
            )


@pytest.mark.parametrize("language", [None, "zz-unsupported", "fr"])
def test_word_rejects_missing_unsupported_or_disabled_language(
    client, connection, package, language
):
    imported = upload(client, package)
    assert imported.status_code == 201, imported.text
    try:
        if language == "fr":
            connection.execute(
                "SELECT set_config('app.change_reason','Disposable Word test',true)"
            )
            connection.execute(
                "UPDATE supported_languages SET is_enabled=false WHERE language_tag='fr'"
            )
            connection.commit()
        params = {"format": "docx"}
        if language is not None:
            params["language"] = language
        response = client.get(
            f"/api/v1/classification-schemes/{imported.json()['id']}/export",
            params=params,
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"].endswith("unsupported_language")
    finally:
        if language == "fr":
            with psycopg.connect(os.environ["DATABASE_URL"]) as restore:
                restore.execute(
                    "SELECT set_config('app.change_reason','Restore disposable language',true)"
                )
                restore.execute(
                    "UPDATE supported_languages SET is_enabled=true WHERE language_tag='fr'"
                )


@pytest.mark.parametrize("kind", ["json", "csv"])
@pytest.mark.parametrize(
    "shape", ["empty", "broad", "deep", "multiple_roots", "deactivated", "long"]
)
def test_api_hierarchy_shapes(client, package, kind, shape):
    scheme = package["data"]["scheme"]
    template = copy.deepcopy(scheme["classifications"][0])
    template["retention_rule"] = None
    if shape == "empty":
        scheme["classifications"] = []
    elif shape in ("deep", "broad", "multiple_roots"):
        count = 80 if shape != "multiple_roots" else 3
        scheme["classifications"] = [
            dict(
                template,
                source_id=str(100 + i),
                code=f"{i:04}",
                parent_code=(
                    f"{i-1:04}"
                    if shape == "deep" and i
                    else "0000" if shape == "broad" and i else None
                ),
            )
            for i in range(count)
        ]
    elif shape == "long":
        for entity in [scheme, *scheme["classifications"]]:
            entity["description"] = (
                "Administrative evidence وثائق إدارية — preserve exact mixed-script text.\n"
                * 8
            )
    else:
        scheme["date_deactivated"] = "2026-01-02T08:00:00.000000Z"
        scheme["classifications"][0]["date_deactivated"] = scheme["date_deactivated"]
    package["manifest"]["counts"] = dict(
        classifications=len(scheme["classifications"]),
        retention_rules=sum(
            c["retention_rule"] is not None for c in scheme["classifications"]
        ),
    )
    seal(package)
    result = upload(client, package, kind)
    assert result.status_code == 201, result.text
    sid = result.json()["id"]
    exported = client.get(
        f"/api/v1/classification-schemes/{sid}/export", params={"format": kind}
    )
    assert exported.status_code == 200, exported.text
    actual = decode(exported.content, kind)["data"]["scheme"]
    assert len(actual["classifications"]) == len(scheme["classifications"])
    assert [(c["code"], c["parent_code"]) for c in actual["classifications"]] == [
        (c["code"], c["parent_code"]) for c in scheme["classifications"]
    ]
    for language in ("en", "ar", "fr"):
        word = client.get(
            f"/api/v1/classification-schemes/{sid}/export",
            params={"format": "docx", "language": language},
        )
        assert word.status_code == 200, word.text
        if kind == "json" and os.environ.get("TRANSFER_QA_DIR"):
            from pathlib import Path

            Path(os.environ["TRANSFER_QA_DIR"]).mkdir(parents=True, exist_ok=True)
            Path(
                os.environ["TRANSFER_QA_DIR"], f"scheme-{shape}-{language}.docx"
            ).write_bytes(word.content)
        from lxml import etree

        with ZipFile(io.BytesIO(word.content)) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            assert len(root.xpath("//w:tbl", namespaces=ns)) == 1 + sum(
                c["parent_code"] is None for c in scheme["classifications"]
            )


def test_checked_in_fixtures_match():
    from pathlib import Path

    root = Path(__file__).with_name("fixtures")
    assert decode((root / "scheme.json").read_bytes(), "json") == decode(
        (root / "scheme.csv").read_bytes(), "csv"
    )


@pytest.mark.parametrize("kind", ["json", "csv"])
def test_first_use_and_publication_workflow(client, connection, package, kind):
    scheme = package["data"]["scheme"]
    scheme["date_first_used"] = "2026-01-02T08:00:00.123456Z"
    for item in scheme["classifications"]:
        item["date_first_used"] = scheme["date_first_used"]
    seal(package)
    response = upload(client, package, kind)
    assert response.status_code == 201, response.text
    sid = response.json()["id"]
    row = connection.execute(
        "SELECT * FROM classification_schemes WHERE id=%s", (sid,)
    ).fetchone()
    assert (
        row["date_first_used"].microsecond == 123456 and row["date_published"] is None
    )
    published = client.post(
        f"/api/v1/classification-schemes/{sid}/publish",
        headers={"If-Match": str(row["version"])},
    )
    assert published.status_code == 200, published.text
    assert published.json()["date_published"] is not None
    denied = client.post(
        f"/api/v1/classification-schemes/{sid}/unpublish",
        headers={
            "If-Match": str(published.json()["version"]),
            "X-Change-Reason": "Verify imported first-use governance",
        },
    )
    assert denied.status_code == 409, denied.text


@pytest.mark.parametrize(
    "mutation",
    [
        "manifest",
        "array_order",
        "string",
        "surrogate",
        "infinite",
        "nested_duplicate",
        "unknown_version",
        "checksum_duplicate",
    ],
)
def test_integrity_edge_cases(package, mutation):
    raw = json.dumps(package).encode()
    if mutation == "manifest":
        raw = raw.replace(b"source@test.invalid", b"other@test.invalid")
    if mutation == "array_order":
        package["data"]["scheme"]["classifications"].reverse()
        raw = json.dumps(package).encode()
    if mutation == "string":
        raw = raw.replace(b"Administrative records", b"Administrative records ")
    if mutation == "surrogate":
        raw = raw.replace(b"Administrative records", b"\\ud800")
    if mutation == "infinite":
        raw = raw.replace(b'"classifications": 2', b'"classifications": 1e999')
    if mutation == "nested_duplicate":
        raw = raw.replace(b'"edition": "2026"', b'"edition": "2026", "edition": "2026"')
    if mutation == "unknown_version":
        raw = raw.replace(b'"format_version": "1.0"', b'"format_version": "99.0"')
    if mutation == "checksum_duplicate":
        checksum = package["manifest"]["checksum"]["value"].encode()
        raw = raw.replace(
            b'"value": "' + checksum + b'"',
            b'"value": "' + checksum + b'", "value": "' + checksum + b'"',
        )
    with pytest.raises(TransferError):
        decode(raw, "json")


def test_jcs_reference_vector():
    import rfc8785

    # RFC 8785 section 3.2.2 example: number normalization, escaping, and key order.
    source = {
        "numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27],
        "literals": [None, True, False],
    }
    assert (
        rfc8785.dumps(source)
        == b'{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27]}'
    )


def test_anonymous_transfer_denied(client, package):
    import httpx
    from fastapi.testclient import TestClient
    from backend.services.api.main import app

    anonymous = TestClient(app)
    try:
        assert upload(anonymous, package).status_code == 401
        assert (
            anonymous.get(
                "/api/v1/classification-schemes/1/export", params={"format": "json"}
            ).status_code
            == 401
        )
    finally:
        anonymous.close()


@pytest.mark.parametrize("kind", ["json", "csv"])
def test_bigint_maximum_preserved(client, package, kind):
    maximum = 9223372036854775807
    scheme = package["data"]["scheme"]
    scheme["source_id"] = str(maximum)
    scheme["version"] = str(maximum)
    for index, item in enumerate(scheme["classifications"]):
        item["source_id"] = str(maximum - index)
        item["version"] = str(maximum)
        if item["retention_rule"]:
            item["retention_rule"]["source_id"] = str(maximum)
            item["retention_rule"]["version"] = str(maximum)
    package["manifest"]["exported_by"]["source_user_id"] = str(maximum)
    seal(package)
    result = upload(client, package, kind)
    assert result.status_code == 201, result.text
    response = client.get(
        f"/api/v1/classification-schemes/{result.json()['id']}/export",
        params={"format": kind},
    )
    assert response.status_code == 200, response.text
    exported = decode(response.content, kind)
    assert exported["data"]["scheme"]["version"] == str(maximum)
    assert exported["data"]["scheme"]["source_id"] != str(maximum)


def test_resource_limits(package):
    from backend.services.api.scheme_transfer.codec import MAX_BYTES

    with pytest.raises(TransferError, match="file_too_large"):
        decode(b" " * (MAX_BYTES + 1), "json")
    scheme = package["data"]["scheme"]
    template = dict(scheme["classifications"][0], retention_rule=None)
    scheme["classifications"] = [
        dict(template, source_id=str(i + 1), code=str(i)) for i in range(10001)
    ]
    package["manifest"]["counts"] = dict(classifications=10001, retention_rules=0)
    with pytest.raises(TransferError):
        seal(package)


@pytest.mark.parametrize("kind", ["json", "csv"])
def test_every_entity_has_source_mapping_and_actual_actor(
    client, connection, package, kind
):
    response = upload(client, package, kind)
    assert response.status_code == 201, response.text
    actual_actor = connection.execute(
        "SELECT id FROM users WHERE email='transfer@test.invalid'"
    ).fetchone()["id"]
    events = connection.execute(
        "SELECT * FROM event_history WHERE metadata->'classification_scheme_import'->'manifest'->>'export_id'=%s",
        (package["manifest"]["export_id"],),
    ).fetchall()
    assert len(events) == 4
    assert {row["entity_type"] for row in events} == {
        "classification_scheme",
        "classification",
        "classification_retention_rule",
    }
    for event in events:
        assert event["operation"] == "CREATE" and event["actor_user_id"] == actual_actor
        provenance = event["metadata"]["classification_scheme_import"]
        assert provenance["manifest"] == package["manifest"]
        assert provenance["source_scheme_id"] == package["data"]["scheme"]["source_id"]
        assert str(event["entity_id"]) == str(event["after_state"]["id"])
        assert str(event["entity_id"]) != provenance["source_entity"]["source_id"]


@pytest.mark.parametrize("kind", ["json", "csv"])
def test_case_variant_classification_codes(client, package, kind):
    root, child = package["data"]["scheme"]["classifications"]
    root["code"] = "A"
    child["code"] = "a"
    child["parent_code"] = "A"
    seal(package)
    assert upload(client, package, kind).status_code == 409
