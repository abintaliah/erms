"""Integration tests run only through tools/test_messaging.py's disposable DBs."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta, timezone
import os
from uuid import uuid4
import psycopg
from psycopg.rows import dict_row
import pytest
from .test_global_privilege_enforcement import _account, _bearer
from backend.services.api.messaging.models import Send
from backend.services.api.messaging.service import send
from backend.services.api.messaging.transactions import run

PREFIX = "/api/v1/messages"
EXCHANGE = "messaging.user_messages.exchange"


def account(client, privileges=(EXCHANGE,)):
    client.headers["X-CSRF-Token"] = client.cookies.get("erms_csrf", "")
    return _account(client, privileges=privileges)


def payload(*users, **changes):
    return {
        "request_id": str(uuid4()),
        "subject": "Durable message",
        "body_rich_text": "<p>Hello</p>",
        "selectors": [
            {"selector_kind": "user", "target_id": u, "recipient_type": "to"}
            for u in users
        ],
        **changes,
    }


def post(client, token, data):
    return client.post(PREFIX + "/send", headers=_bearer(token), json=data)


def db():
    assert (
        "_test_" in os.environ["DATABASE_URL"]
    ), "Disposable messaging test database required"
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def test_send_read_receipts_and_pagination(client):
    sender, uid, _ = account(client)
    recipient, rid, _ = account(client)
    other, oid, _ = account(client)
    data = payload(rid, oid, read_receipt_requested=True)
    sent = post(client, sender, data)
    assert sent.status_code == 200, sent.text
    result = sent.json()
    assert len(result["deliveries"]) == 2
    did = next(d["id"] for d in result["deliveries"] if d["recipient_user_id"] == rid)
    assert client.get(PREFIX + "/inbox", headers=_bearer(sender)).json()["items"] == []
    got = client.get(PREFIX + "/inbox/" + did, headers=_bearer(recipient))
    assert got.status_code == 200, got.text
    assert got.json()["body_rich_text"] == "<p>Hello</p>" and not got.json()["is_read"]
    assert (
        client.get(PREFIX + "/inbox/" + did, headers=_bearer(other)).status_code == 404
    )
    assert (
        client.post(
            PREFIX + "/inbox/" + did + "/read", headers=_bearer(other)
        ).status_code
        == 404
    )
    for _ in range(2):
        assert (
            client.post(
                PREFIX + "/inbox/" + did + "/read", headers=_bearer(recipient)
            ).status_code
            == 200
        )
    receipt_url = PREFIX + "/outbox/" + result["envelope_id"] + "/recipients"
    receipts = client.get(receipt_url, headers=_bearer(sender)).json()["items"]
    assert next(x for x in receipts if x["recipient_user_id"] == rid)["read_at"]
    assert next(x for x in receipts if x["recipient_user_id"] == oid)["read_at"] is None
    assert client.get(receipt_url, headers=_bearer(other)).status_code == 404
    for _ in range(3):
        assert post(client, sender, payload(rid)).status_code == 200
    seen = []
    cursor = None
    while True:
        page = client.get(
            PREFIX + "/inbox",
            params={"limit": 2, **({"cursor": cursor} if cursor else {})},
            headers=_bearer(recipient),
        ).json()
        seen.extend(i["id"] for i in page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 4
    first = client.get(
        PREFIX + "/catch-up?after=0&limit=2", headers=_bearer(recipient)
    ).json()
    assert first["next_cursor"] == 2 and first["has_more"]
    second = client.get(
        PREFIX + "/catch-up?after=2&limit=2", headers=_bearer(recipient)
    ).json()
    assert second["next_cursor"] == 4 and not second["has_more"]
    assert (
        client.get(PREFIX + "/inbox?limit=51", headers=_bearer(recipient)).status_code
        == 422
    )
    assert (
        client.get(
            PREFIX + "/inbox?cursor=invalid", headers=_bearer(recipient)
        ).status_code
        == 422
    )
    assert (
        client.get(PREFIX + "/unread-count", headers=_bearer(recipient)).json()[
            "unread_count"
        ]
        == 3
    )


def test_idempotency_concurrent_fanout_and_rollback(client):
    sender, uid, _ = account(client)
    _, rid, _ = account(client)
    _, oid, _ = account(client)
    data = Send(**payload(rid, oid))

    def worker(_):
        return run(uid, lambda c: send(c, uid, data))

    with ThreadPoolExecutor(max_workers=4) as executor:
        outcomes = list(executor.map(worker, range(8)))
    assert len({x["envelope_id"] for x in outcomes}) == 1
    assert (
        post(
            client, sender, {**data.model_dump(mode="json"), "subject": "different"}
        ).status_code
        == 409
    )

    def independent(_):
        return run(uid, lambda c: send(c, uid, Send(**payload(rid, oid))))

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(independent, range(8)))
    with db() as c:
        sequences = c.execute(
            "SELECT mailbox_sequence FROM message_deliveries WHERE recipient_user_id=%s ORDER BY mailbox_sequence",
            (rid,),
        ).fetchall()
        assert [x["mailbox_sequence"] for x in sequences] == list(range(1, 10))
        c.execute(
            "CREATE FUNCTION reject_test_delivery() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.recipient_user_id="
            + str(oid)
            + " THEN RAISE EXCEPTION 'injected failure'; END IF; RETURN NEW; END $$"
        )
        c.execute(
            "CREATE TRIGGER reject_test_delivery BEFORE INSERT ON message_deliveries FOR EACH ROW EXECUTE FUNCTION reject_test_delivery()"
        )
    try:
        with pytest.raises(psycopg.errors.RaiseException):
            independent(0)
    finally:
        with db() as c:
            c.execute("DROP TRIGGER reject_test_delivery ON message_deliveries")
            c.execute("DROP FUNCTION reject_test_delivery()")
    with db() as c:
        assert (
            c.execute("SELECT count(*) AS n FROM message_envelopes").fetchone()["n"]
            == 9
        )
        assert (
            c.execute(
                "SELECT last_sequence FROM message_mailboxes WHERE user_id=%s", (rid,)
            ).fetchone()["last_sequence"]
            == 9
        )
        assert (
            c.execute("SELECT count(*) AS n FROM message_request_receipts").fetchone()[
                "n"
            ]
            == 9
        )


def test_sanitization_validation_and_sender_boundary(client):
    token, uid, _ = account(client)
    _, rid, _ = account(client)
    data = payload(
        rid,
        subject=" e\u0301 ",
        body_rich_text='<p onclick="evil()">safe<script>alert(1)</script><img src=x onerror=evil()><strong>bold</strong></p>',
    )
    result = post(client, token, data)
    assert result.status_code == 200, result.text
    got = client.get(
        PREFIX + "/outbox/" + result.json()["envelope_id"], headers=_bearer(token)
    ).json()
    assert (
        got["subject"] == "é"
        and got["body_rich_text"] == "<p>safe<strong>bold</strong></p>"
    )
    for changes in (
        {"sender_kind": "system"},
        {"sender_user_id": rid},
        {"subject": " "},
        {"subject": "x" * 256},
        {"body_rich_text": "é" * 32769},
        {"body_rich_text": '<a href="javascript:alert(1)">x</a>'},
        {"body_rich_text": '<a href="https://example.com/records/4">x</a>'},
        {
            "action_due_date": str(date.today() - timedelta(days=1)),
            "action_required": True,
        },
    ):
        assert post(client, token, payload(rid, **changes)).status_code == 422, changes
    assert post(client, token, payload(uid)).status_code == 422
    assert (
        post(
            client,
            token,
            payload(
                rid,
                selectors=[
                    {"selector_kind": "user", "target_id": rid, "recipient_type": "cc"}
                ],
            ),
        ).status_code
        == 422
    )
    none, _, _ = account(client, ())
    assert post(client, none, payload(rid)).status_code == 403
    assert client.get(PREFIX + "/outbox", headers=_bearer(none)).status_code == 403


def test_expansion_snapshot_and_privilege_revocation(client):
    sender, uid, _ = account(client)
    receiver, rid, role = account(client)
    _, oid, _ = account(client)
    with db() as c:
        c.execute(
            "INSERT INTO user_role_assignments(user_id,role_id) VALUES (%s,%s)",
            (oid, role),
        )
        org = c.execute(
            "SELECT org_unit_id FROM roles WHERE id=%s", (role,)
        ).fetchone()["org_unit_id"]
    selectors = [
        {"selector_kind": "role", "target_id": role, "recipient_type": "cc"},
        {"selector_kind": "org_unit", "target_id": org, "recipient_type": "to"},
        {"selector_kind": "user", "target_id": rid, "recipient_type": "cc"},
    ]
    result = post(client, sender, payload(selectors=selectors))
    assert result.status_code == 200, result.text
    assert len(result.json()["deliveries"]) == 2
    assert {d["recipient_type"] for d in result.json()["deliveries"]} == {"to"}
    with db() as c:
        c.execute("UPDATE users SET name='Changed' WHERE id=%s", (rid,))
        c.execute("DELETE FROM user_role_assignments WHERE user_id=%s", (rid,))
    assert (
        client.get(PREFIX + "/inbox", headers=_bearer(receiver)).json()["items"] == []
    )
    assert (
        client.get(PREFIX + "/catch-up", headers=_bearer(receiver)).json()["items"]
        == []
    )
    receipts = client.get(
        PREFIX + "/outbox/" + result.json()["envelope_id"] + "/recipients",
        headers=_bearer(sender),
    ).json()["items"]
    assert (
        next(d for d in receipts if d["recipient_user_id"] == rid)["recipient_name"]
        != "Changed"
    )
    assert all("read_at" not in d for d in receipts)
    options = client.get(PREFIX + "/recipients/user?limit=1", headers=_bearer(sender))
    assert options.status_code == 200, options.text
    assert len(options.json()["items"]) == 1
    assert (
        client.get(
            PREFIX + "/recipients/role?limit=51", headers=_bearer(sender)
        ).status_code
        == 422
    )


def test_clearance_recheck_is_non_disclosing(client):
    sender, uid, srole = account(client)
    receiver, rid, rrole = account(client)
    _, low, _ = account(client)
    with db() as c:
        high = c.execute("SELECT id FROM security_levels WHERE code='S'").fetchone()[
            "id"
        ]
        c.execute(
            "UPDATE roles SET security_level_id=%s WHERE id=ANY(%s)",
            (high, [srole, rrole]),
        )
    assert post(client, sender, payload(low, security_level_id=high)).status_code == 422
    result = post(client, sender, payload(rid, security_level_id=high))
    assert result.status_code == 200, result.text
    did = result.json()["deliveries"][0]["id"]
    with db() as c:
        c.execute(
            "UPDATE roles SET security_level_id=(SELECT id FROM security_levels WHERE code='G') WHERE id=%s",
            (rrole,),
        )
    row = client.get(PREFIX + "/inbox", headers=_bearer(receiver)).json()["items"][0]
    assert row["availability"] == "restricted"
    assert not set(row) & {
        "sender_name",
        "subject",
        "priority",
        "security_level_id",
        "body_rich_text",
        "resource_links",
        "action_required",
    }
    assert (
        client.get(PREFIX + "/unread-count", headers=_bearer(receiver)).json()[
            "unread_count"
        ]
        == 1
    )
    assert (
        client.post(
            PREFIX + "/inbox/" + did + "/read", headers=_bearer(receiver)
        ).status_code
        == 403
    )
    assert (
        client.get(PREFIX + "/inbox?priority=normal", headers=_bearer(receiver)).json()[
            "items"
        ]
        == []
    )
    with db() as c:
        c.execute("UPDATE roles SET security_level_id=%s WHERE id=%s", (high, rrole))
    assert (
        client.get(PREFIX + "/inbox/" + did, headers=_bearer(receiver)).json()[
            "subject"
        ]
        == "Durable message"
    )


def test_resource_authorization_security_and_batching(client, aggregation, record):
    sender = client.cookies["erms_session"]
    receiver, rid, rrole = account(
        client, (EXCHANGE, "aggregation.view", "record.view")
    )
    with db() as c:
        c.execute(
            "UPDATE roles SET is_information_governance=true WHERE id=%s", (rrole,)
        )
    token = str(uuid4())
    link = {"link_token": token, "resource_kind": "record", "target_id": record["id"]}
    data = payload(
        rid,
        resource_links=[link],
        body_rich_text=f'<p><a href="wathiq-resource:{token}">Secret client label</a></p>',
    )
    result = post(client, sender, data)
    assert result.status_code == 200, result.text
    did = result.json()["deliveries"][0]["id"]
    got = client.get(PREFIX + "/inbox/" + did, headers=_bearer(receiver)).json()
    assert (
        got["resource_links"][0]["available"]
        and got["resource_links"][0]["title"] == "Example record"
    )
    assert "Secret client label" not in got["body_rich_text"]
    with db() as c:
        c.execute(
            "UPDATE roles SET is_information_governance=false WHERE id=%s", (rrole,)
        )
    got = client.get(PREFIX + "/inbox/" + did, headers=_bearer(receiver)).json()
    assert got["resource_links"] == [
        {
            "link_token": token,
            "available": False,
            "reason_code": "message_resource_unavailable",
        }
    ]
    assert client.get(PREFIX + "/inbox", headers=_bearer(receiver)).json()["items"][0][
        "has_unavailable_resources"
    ]
    assert (
        post(
            client,
            receiver,
            payload(1, resource_links=[link], body_rich_text=data["body_rich_text"]),
        ).status_code
        == 422
    )
    with db() as c:
        c.execute(
            "UPDATE roles SET security_level_id=(SELECT id FROM security_levels WHERE code='S') WHERE id=1"
        )
        c.execute(
            "UPDATE aggregations SET security_level_id=(SELECT id FROM security_levels WHERE code='S') WHERE id=%s",
            (aggregation["id"],),
        )
        c.execute(
            "UPDATE records SET security_level_id=(SELECT id FROM security_levels WHERE code='R') WHERE id=%s",
            (record["id"],),
        )
    assert post(client, sender, {**data, "request_id": str(uuid4())}).status_code == 422
    options = client.get(PREFIX + "/resources/record", headers=_bearer(sender)).json()[
        "items"
    ]
    assert options[0]["reason_code"] == "message_resource_level_too_high"
    got = client.get(
        PREFIX + "/outbox/" + result.json()["envelope_id"], headers=_bearer(sender)
    ).json()
    assert not got["resource_links"][0]["available"]
    from backend.services.api.messaging.reading import inbox

    class Counted:
        def __init__(self, c):
            self.c = c
            self.queries = 0

        def execute(self, *args, **kwargs):
            self.queries += 1
            return self.c.execute(*args, **kwargs)

    with db() as c:
        c.execute("SELECT set_config('app.user_id',%s,true)", (str(rid),))
        counted = Counted(c)
        inbox(counted, rid, 50)
        assert counted.queries <= 9


def test_database_immutability_and_restart_durability(client):
    import json
    import subprocess
    import sys

    sender, uid, _ = account(client)
    _, rid, _ = account(client)
    result = post(client, sender, payload(rid))
    assert result.status_code == 200, result.text
    envelope = result.json()["envelope_id"]
    did = result.json()["deliveries"][0]["id"]
    mutations = [
        ("UPDATE message_envelopes SET subject=%s WHERE id=%s", ("tampered", envelope)),
        ("DELETE FROM message_deliveries WHERE id=%s", (did,)),
        (
            "UPDATE message_addressees SET recipient_name=%s WHERE envelope_id=%s",
            ("tampered", envelope),
        ),
        (
            "UPDATE message_recipient_selectors SET display_name=%s WHERE envelope_id=%s",
            ("tampered", envelope),
        ),
        ("UPDATE message_mailboxes SET last_sequence=0 WHERE user_id=%s", (rid,)),
        (
            "DELETE FROM message_request_receipts WHERE result_envelope_id=%s",
            (envelope,),
        ),
        (
            "INSERT INTO message_recipient_selectors(envelope_id,recipient_type,selector_kind,user_id,display_name,ordinal) VALUES (%s,'cc','user',%s,'added',0)",
            (envelope, rid),
        ),
    ]
    for statement, args in mutations:
        with pytest.raises(psycopg.errors.CheckViolation):
            with db() as c:
                c.execute(statement, args)
    code = """import os,json,psycopg
from psycopg.rows import dict_row
from backend.services.api.messaging.reading import delivery
with psycopg.connect(os.environ['DATABASE_URL'],row_factory=dict_row) as c:
 c.execute("SELECT set_config('app.user_id',%s,true)",(os.environ['TEST_RECIPIENT'],))
 print(json.dumps(delivery(c,int(os.environ['TEST_RECIPIENT']),os.environ['TEST_DELIVERY']),default=str))
"""
    output = subprocess.check_output(
        [sys.executable, "-c", code],
        env={**os.environ, "TEST_RECIPIENT": str(rid), "TEST_DELIVERY": did},
        text=True,
    )
    assert json.loads(output)["subject"] == "Durable message"


def test_limits_and_due_boundary(client, monkeypatch):
    from backend.services.api.messaging.config import LIMITS

    sender, uid, _ = account(client)
    _, rid, _ = account(client)
    _, oid, _ = account(client)
    monkeypatch.setitem(LIMITS, "MAX_RECIPIENTS_PER_SEND", 1)
    assert post(client, sender, payload(rid, oid)).status_code == 422
    with db() as c:
        assert (
            c.execute("SELECT count(*) AS n FROM message_envelopes").fetchone()["n"]
            == 0
        )
        c.execute(
            "INSERT INTO user_preferences(user_id,language_tag,working_timezone) VALUES (%s,'en','America/New_York')",
            (uid,),
        )
    invalid_date = post(
        client, sender, payload(rid, action_required=True, action_due_date="9999-12-31")
    )
    assert invalid_date.status_code == 422
    assert invalid_date.json()["detail"]["code"] == "message_due_date_out_of_range"
    result = post(
        client, sender, payload(rid, action_required=True, action_due_date="2030-03-10")
    )
    assert result.status_code == 200, result.text
    with db() as c:
        row = c.execute(
            "SELECT action_due_at,action_due_timezone FROM message_envelopes WHERE id=%s",
            (result.json()["envelope_id"],),
        ).fetchone()
        assert (
            row["action_due_at"].astimezone(timezone.utc).isoformat()
            == "2030-03-11T04:00:00+00:00"
        )
        assert row["action_due_timezone"] == "America/New_York"


def test_storage_model_and_deferred_integrity(client):
    sender, uid, _ = account(client)
    _, rid, _ = account(client)
    sent = post(client, sender, payload(rid, action_required=True)).json()
    envelope = sent["envelope_id"]
    did = sent["deliveries"][0]["id"]
    with db() as c:
        types = {
            (r["table_name"], r["column_name"]): r["data_type"]
            for r in c.execute(
                "SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND (table_name LIKE 'message_%' OR table_name LIKE 'system_notification_%')"
            ).fetchall()
        }
        assert len({table for table, column in types}) == 20
        assert types[("message_capture_drafts", "capture_id")] == "uuid"
        assert types[("message_capture_drafts", "draft_id")] == "bigint"
        for table in (
            "message_envelopes",
            "message_deliveries",
            "message_drafts",
            "message_action_amendments",
            "message_record_captures",
            "system_notification_configuration_versions",
        ):
            assert types[(table, "id")] == "uuid"
        for table in (
            "message_recipient_selectors",
            "message_resource_links",
            "message_record_capture_components",
            "message_request_receipts",
        ):
            assert types[(table, "id")] == "bigint"
        assert types[("message_mailboxes", "user_id")] == "bigint"
    with pytest.raises(psycopg.errors.CheckViolation):
        with db() as c:
            c.execute(
                "INSERT INTO message_action_completions(original_delivery_id,reply_envelope_id,completed_by_user_id) VALUES (%s,%s,%s)",
                (did, envelope, rid),
            )
    with pytest.raises(psycopg.errors.CheckViolation):
        with db() as c:
            c.execute(
                """INSERT INTO message_action_amendments(id,original_envelope_id,sequence,amendment_kind,previous_action_required,new_action_required,reason,created_by_user_id,request_id)
                VALUES (%s,%s,1,'action_withdrawn',true,false,'Withdraw',%s,%s)""",
                (uuid4(), envelope, uid, uuid4()),
            )
    with pytest.raises(psycopg.errors.CheckViolation):
        with db() as c:
            c.execute(
                """INSERT INTO message_envelopes(id,sender_user_id,sender_name,sender_kind,message_kind,subject,body_rich_text,action_required,read_receipt_requested,expires_at,request_id)
                VALUES (%s,%s,'Snapshot','user','user_message','Incomplete','<p>Missing fanout</p>',false,false,CURRENT_TIMESTAMP+INTERVAL '1 day',%s)""",
                (uuid4(), uid, uuid4()),
            )
    draft = uuid4()
    with db() as c:
        c.execute(
            """INSERT INTO message_drafts(id,owner_user_id,action_required,read_receipt_requested,expires_at,related_delivery_id)
            VALUES (%s,%s,false,false,CURRENT_TIMESTAMP+INTERVAL '180 days',%s)""",
            (draft, uid, uuid4()),
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        with db() as c:
            c.execute(
                "UPDATE message_drafts SET subject='Lost update' WHERE id=%s", (draft,)
            )
    with db() as c:
        assert (
            c.execute(
                "UPDATE message_drafts SET subject='Versioned',version=version+1 WHERE id=%s RETURNING version",
                (draft,),
            ).fetchone()["version"]
            == 2
        )


def test_expansion_excludes_descendants_inactive_and_expired_assignments(client):
    sender, uid, _ = account(client)
    _, rid, role = account(client)
    _, oid, _ = account(client)
    with db() as c:
        org = c.execute(
            "SELECT org_unit_id FROM roles WHERE id=%s", (role,)
        ).fetchone()["org_unit_id"]
        child = c.execute(
            "INSERT INTO org_units(parent_org_unit_id,code,name) VALUES (%s,'msg-child','Child') RETURNING id",
            (org,),
        ).fetchone()["id"]
        c.execute(
            "UPDATE roles SET org_unit_id=%s WHERE id IN (SELECT role_id FROM user_role_assignments WHERE user_id=%s)",
            (child, oid),
        )
    selectors = [
        {"selector_kind": "org_unit", "target_id": org, "recipient_type": "to"}
    ]
    result = post(client, sender, payload(selectors=selectors))
    assert result.status_code == 200, result.text
    assert [d["recipient_user_id"] for d in result.json()["deliveries"]] == [rid]
    with db() as c:
        c.execute(
            "UPDATE user_role_assignments SET valid_until=CURRENT_TIMESTAMP WHERE user_id=%s",
            (rid,),
        )
    assert post(client, sender, payload(selectors=selectors)).status_code == 422


def test_minimal_receipt_prevents_recreation_after_purge(client):
    from hashlib import sha256
    import json

    sender, uid, _ = account(client)
    _, rid, _ = account(client)
    data = payload(rid)
    canonical = Send(**data).model_dump(mode="json")
    for key in ("relationship_kind","related_delivery_id","related_envelope_id","complete_action"):
        canonical.pop(key)
    fingerprint = sha256(
        json.dumps(
            canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    with db() as c:
        c.execute(
            """INSERT INTO message_request_receipts(operation_kind,principal_user_id,request_id,request_fingerprint,result_envelope_id,result_purged_at)
            VALUES ('send',%s,%s,%s,%s,CURRENT_TIMESTAMP)""",
            (uid, data["request_id"], fingerprint, uuid4()),
        )
    assert post(client, sender, data).status_code == 410
    assert post(client, sender, {**data, "subject": "new contents"}).status_code == 409
    with db() as c:
        assert (
            c.execute("SELECT count(*) AS n FROM message_envelopes").fetchone()["n"]
            == 0
        )


def test_body_byte_limits_token_integrity_and_encoded_internal_urls(client):
    sender, uid, _ = account(client)
    _, rid, _ = account(client)
    assert (
        post(client, sender, payload(rid, body_rich_text="é" * 65537)).status_code
        == 413
    )
    assert (
        post(client, sender, payload(rid, body_rich_text="é" * 32768)).status_code
        == 200
    )
    token = str(uuid4())
    for markup in (
        '<a href="https://example.invalid/%72ecords/1">Hidden internal path</a>',
        '<a href="https://example.invalid/#/records/1">Internal fragment</a>',
        '<a href="data:text/html,unsafe">Data URL</a>',
        f'<a href="wathiq-resource:{token}">Unregistered</a>',
    ):
        assert (
            post(client, sender, payload(rid, body_rich_text=markup)).status_code == 422
        )
    from backend.services.api.messaging.content import body

    for markup in (
        "<svg><script>bad()</script></svg><p>ok</p>",
        "<math><annotation-xml><svg onload=bad()></svg></annotation-xml></math><p>ok</p>",
        "<template><p>hidden</p></template><p>ok</p>",
    ):
        assert body(markup, []) == "<p>ok</p>"
    valid = body(
        '<a href="https://example.invalid/?a=1&amp;b=2" onclick="bad()">external</a>',
        [],
    )
    assert "onclick" not in valid and 'rel="noopener noreferrer"' in valid


def test_commit_visibility_and_cursor_high_water(client):
    from threading import Event
    from backend.services.api.messaging.reading import inbox

    sender, uid, _ = account(client)
    recipient, rid, _ = account(client)
    written = Event()
    release = Event()
    data = Send(**payload(rid))

    def transaction():
        def operation(c):
            result = send(c, uid, data)
            written.set()
            assert release.wait(20)
            return result

        return run(uid, operation)

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(transaction)
        try:
            assert written.wait(20)
            page = run(rid, lambda c: inbox(c, rid, 1, after=0))
            assert page["items"] == [] and page["next_cursor"] == 0
        finally:
            release.set()
        committed = pending.result()
    page = client.get(
        PREFIX + "/catch-up?after=0&limit=1", headers=_bearer(recipient)
    ).json()
    assert page["items"][0]["id"] == str(committed["deliveries"][0]["id"])
    assert page["next_cursor"] == 1
    with db() as c:
        # A committed unused sequence is a valid gap; catch-up must progress.
        c.execute(
            "UPDATE message_mailboxes SET last_sequence=last_sequence+1 WHERE user_id=%s",
            (rid,),
        )
    page = client.get(PREFIX + "/catch-up?after=1", headers=_bearer(recipient)).json()
    assert page["items"] == [] and page["next_cursor"] == 2


def test_privilege_seed_and_configuration_validation(client):
    import subprocess
    import sys

    with db() as c:
        grants = c.execute(
            "SELECT p.code,v.code AS privilege FROM profiles p JOIN profile_privileges x ON x.profile_id=p.id JOIN privileges v ON v.id=x.privilege_id WHERE v.code LIKE 'messaging.%' AND p.code IN ('ALL_PRIVS','SYS_ADMIN')"
        ).fetchall()
        assert {(r["code"], r["privilege"]) for r in grants} == {
            ("ALL_PRIVS", EXCHANGE),
            ("ALL_PRIVS", "messaging.monitor"),
            ("ALL_PRIVS", "messaging.notifications.administer"),
            ("SYS_ADMIN", "messaging.monitor"),
            ("SYS_ADMIN", "messaging.notifications.administer"),
        }
    for setting, value in [
        ("MAX_RECIPIENTS_PER_SEND", "0"),
        ("MAX_RESOURCE_LINKS", "invalid"),
        ("RETENTION_WARNING_DAYS", "1095"),
        ("DRAFT_ACTIVE_DAYS", "-1"),
    ]:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from backend.services.api.messaging.config import LIMITS",
            ],
            env={**os.environ, "MESSAGING_" + setting: value},
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0 and "MESSAGING_" in result.stderr


def test_system_only_inbox_and_language_variant(client):
    from backend.services.api.messaging.transactions import run
    from backend.services.api.messaging.service import EXCHANGE

    receiver, rid, _ = account(client, ())
    envelope, delivery_id, configuration, request_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    with db() as c:
        c.execute(
            "INSERT INTO system_notification_producers(producer_code,feature_code,event_type,required_for_business_commit,contract_version,contract_definition) VALUES ('test.kernel','test','occurred',false,1,'{}')"
        )
        c.execute(
            "INSERT INTO system_notification_configuration_versions(id,producer_code,version,enabled,subject_template,body_template_rich_text,audience_mode,resource_presentation,operational_owner,change_reason,created_by_user_id) VALUES (%s,'test.kernel',1,true,'Notice','<p>Notice</p>','static','{}','test','fixture',1)",
            (configuration,),
        )
        c.execute(
            """INSERT INTO message_envelopes(id,sender_name,sender_kind,message_kind,system_producer_code,system_configuration_version_id,source_event_type,source_event_id,subject,body_rich_text,action_required,read_receipt_requested,expires_at,request_id)
            VALUES (%s,'system','system','system_notification','test.kernel',%s,'occurred','one','Notice','<p>Notice</p>',false,false,CURRENT_TIMESTAMP+INTERVAL '1 day',%s)""",
            (envelope, configuration, request_id),
        )
        c.execute(
            "INSERT INTO message_envelope_localizations(envelope_id,language_tag,subject,body_rich_text,direction) VALUES (%s,'ar','إشعار','<p>إشعار</p>','rtl')",
            (envelope,),
        )
        c.execute(
            "INSERT INTO message_recipient_selectors(envelope_id,recipient_type,selector_kind,user_id,display_name,ordinal) VALUES (%s,'to','user',%s,'Recipient',0)",
            (envelope, rid),
        )
        c.execute(
            "INSERT INTO message_addressees(envelope_id,user_id,recipient_name,recipient_type,ordinal) VALUES (%s,%s,'Recipient','to',0)",
            (envelope, rid),
        )
        c.execute(
            "INSERT INTO message_mailboxes(user_id,last_sequence) VALUES (%s,1)", (rid,)
        )
        c.execute(
            "INSERT INTO message_deliveries(id,envelope_id,recipient_user_id,recipient_type,mailbox_sequence,language_tag_at_send) VALUES (%s,%s,%s,'to',1,'en')",
            (delivery_id, envelope, rid),
        )
        c.execute(
            "INSERT INTO message_request_receipts(operation_kind,producer_code,request_id,request_fingerprint,source_event_type,source_event_id,result_envelope_id) VALUES ('send','test.kernel',%s,%s,'occurred','one',%s)",
            (request_id, "0" * 64, envelope),
        )
        c.execute(
            "INSERT INTO user_preferences(user_id,language_tag,working_timezone) VALUES (%s,'ar','Asia/Dubai')",
            (rid,),
        )
    response = client.get(
        PREFIX + "/inbox/" + str(delivery_id), headers=_bearer(receiver)
    )
    assert response.status_code == 200, response.text
    assert (
        response.json()["subject"] == "إشعار" and response.json()["direction"] == "rtl"
    )
    assert response.json()["body_rich_text"] == "<p>إشعار</p>"
    assert (
        len(client.get(PREFIX + "/catch-up", headers=_bearer(receiver)).json()["items"])
        == 1
    )
    assert (
        client.get(PREFIX + "/unread-count", headers=_bearer(receiver)).json()[
            "unread_count"
        ]
        == 1
    )
    assert client.get(PREFIX + "/outbox", headers=_bearer(receiver)).status_code == 403
    assert (
        client.post(
            PREFIX + "/inbox/" + str(delivery_id) + "/read", headers=_bearer(receiver)
        ).status_code
        == 200
    )


def test_lookup_preview_outbox_filters_and_read_timestamp(client):
    sender, uid, _ = account(client)
    receiver, rid, _ = account(client)
    selected = payload(
        rid,
        subject="Action alpha",
        priority="high",
        action_required=True,
        read_receipt_requested=True,
    )
    preview = client.post(
        PREFIX + "/recipients/validate",
        headers=_bearer(sender),
        json={"selectors": selected["selectors"]},
    )
    assert (
        preview.status_code == 200 and preview.json()["expanded_recipient_count"] == 1
    )
    sent = post(client, sender, selected)
    assert sent.status_code == 200, sent.text
    assert sent.json()["expanded_recipient_count"] == 1
    envelope = sent.json()["envelope_id"]
    did = sent.json()["deliveries"][0]["id"]
    caps = client.get(PREFIX + "/capabilities", headers=_bearer(sender)).json()
    assert (
        caps["limits"]["MAX_SELECTORS_PER_SEND"] == 100
        and caps["security_levels"][0]["level_number"] == 0
    )
    for params in (
        {"q": "alpha"},
        {"priority": "high"},
        {"action_state": "outstanding"},
        {"recipient_kind": "user", "recipient_id": rid},
        {"action_required": True},
    ):
        page = client.get(PREFIX + "/outbox", headers=_bearer(sender), params=params)
        assert page.status_code == 200, page.text
        assert page.json()["items"][0]["id"] == envelope
    assert (
        client.get(
            PREFIX + "/outbox?action_state=late", headers=_bearer(sender)
        ).json()["items"]
        == []
    )
    assert (
        client.get(
            PREFIX + "/outbox?recipient_kind=user", headers=_bearer(sender)
        ).status_code
        == 422
    )
    receipt_url = PREFIX + "/outbox/" + envelope + "/recipients"
    client.post(PREFIX + "/inbox/" + did + "/read", headers=_bearer(receiver))
    original = client.get(receipt_url, headers=_bearer(sender)).json()["items"][0][
        "read_at"
    ]
    client.post(PREFIX + "/inbox/" + did + "/read", headers=_bearer(receiver))
    assert (
        client.get(receipt_url, headers=_bearer(sender)).json()["items"][0]["read_at"]
        == original
    )
    with db() as c:
        c.execute(
            "UPDATE users SET date_suspended=CURRENT_TIMESTAMP WHERE id=%s", (rid,)
        )
    assert (
        client.get(
            PREFIX + "/recipients/user",
            params={"target_id": rid},
            headers=_bearer(sender),
        ).json()["items"]
        == []
    )
    assert post(client, sender, payload(rid)).status_code == 422


def test_viewer_localized_message_identity_and_outbox_recipients(client):
    sender, uid, _ = account(client)
    recipient, rid, _ = account(client)
    sent = post(client, sender, payload(rid, read_receipt_requested=True)).json()
    with db() as c:
        snapshot = c.execute('SELECT sender_name FROM message_envelopes WHERE id=%s', (sent['envelope_id'],)).fetchone()['sender_name']
        for identity, name in ((uid, 'المرسل'), (rid, 'المستلم')):
            c.execute("UPDATE users SET translations=jsonb_build_object('ar',jsonb_build_object('name',%s::text)) WHERE id=%s", (name, identity))
            c.execute("INSERT INTO user_preferences(user_id,language_tag,working_timezone) VALUES (%s,'ar','Asia/Dubai') ON CONFLICT(user_id) DO UPDATE SET language_tag='ar'", (identity,))
    message = client.get(PREFIX + '/inbox/' + sent['deliveries'][0]['id'], headers=_bearer(recipient)).json()
    assert message['sender_name'] == 'المرسل'
    assert message['recipient_names'] == ['المستلم']
    assert message['security_level_code'] and message['security_level_number'] == 0
    outbox = client.get(PREFIX + '/outbox', headers=_bearer(sender)).json()['items']
    assert outbox[0]['recipient_names'] == ['المستلم']
    receipts = client.get(PREFIX + '/outbox/' + sent['envelope_id'] + '/recipients', headers=_bearer(sender)).json()['items']
    assert receipts[0]['recipient_name'] == 'المستلم'
    with db() as c:
        assert c.execute('SELECT sender_name FROM message_envelopes WHERE id=%s', (sent['envelope_id'],)).fetchone()['sender_name'] == snapshot
        c.execute("UPDATE users SET translations='{}'::jsonb WHERE id=%s", (uid,))
    fallback = client.get(PREFIX + '/inbox/' + sent['deliveries'][0]['id'], headers=_bearer(recipient)).json()
    assert fallback['sender_name'] == snapshot
