import hashlib
import os
import re
import unittest
from unittest.mock import MagicMock

import psycopg
from fastapi.testclient import TestClient

from backend.services.api.service_authentication import (
    generate_api_key, parse_api_key, resolve_text_indexer_principal,
)

EXAMPLE_KEY = ("wti_01J8Z6M4K7Q2N9V5T3R8C1D0PX."
               "m8GQ1zvF4Kj2Nw6Yx9P_s3Bc7Hd0La5RtUeViAoCqMk")
EXAMPLE_HASH = "f4380efd724ea87ca6cfe53ce595e038aaaad28c1fe58fac23d6234f3b1611fe"


class ServiceAuthenticationTests(unittest.TestCase):
    def test_approved_hash_vector_hashes_only_secret_substring(self):
        identifier, secret = parse_api_key(EXAMPLE_KEY)
        self.assertEqual(identifier, "01J8Z6M4K7Q2N9V5T3R8C1D0PX")
        self.assertEqual(hashlib.sha256(secret.encode("ascii")).hexdigest(), EXAMPLE_HASH)

    def test_parser_rejects_noncanonical_or_ambiguous_keys(self):
        rejected = [EXAMPLE_KEY.lower(), EXAMPLE_KEY + ".extra", EXAMPLE_KEY + "=",
                    EXAMPLE_KEY.replace("wti_", ""), "Bearer " + EXAMPLE_KEY,
                    EXAMPLE_KEY.replace(".", "..", 1)]
        for value in rejected:
            with self.subTest(value=value):
                self.assertIsNone(parse_api_key(value))

    def test_generator_emits_canonical_display_once_material(self):
        key, identifier, digest = generate_api_key()
        self.assertEqual(parse_api_key(key)[0], identifier)
        self.assertRegex(digest, re.compile(r"^[0-9a-f]{64}$"))
        self.assertNotIn(key, digest)

    def test_verifier_checks_lifecycle_account_type_and_exact_privilege(self):
        connection = MagicMock()
        connection.execute.side_effect = [
            MagicMock(fetchone=MagicMock(return_value={
                "credential_id": 7, "service_user_id": 11,
                "credential_identifier": "01J8Z6M4K7Q2N9V5T3R8C1D0PX",
                "secret_hash": EXAMPLE_HASH, "name": "Indexer worker",
            })), MagicMock(),
        ]
        principal = resolve_text_indexer_principal(connection, EXAMPLE_KEY, worker_id="worker-a")
        self.assertEqual(principal.user_id, 11)
        select_sql = connection.execute.call_args_list[0].args[0]
        self.assertIn("credential.status='active'", select_sql)
        self.assertIn("credential.expires_at>CURRENT_TIMESTAMP", select_sql)
        self.assertIn("account.account_type='service'", select_sql)
        self.assertIn("user_has_global_privilege", select_sql)
        self.assertEqual(connection.execute.call_args_list[0].args[1][1], "content.index.execute")

    def test_unknown_and_malformed_keys_fail_without_activity_update(self):
        for value in (EXAMPLE_KEY[:-1] + "x", "wti_invalid"):
            connection = MagicMock()
            connection.execute.return_value.fetchone.return_value = None
            self.assertIsNone(resolve_text_indexer_principal(connection, value))
            self.assertEqual(connection.execute.call_count, 1)


if __name__ == "__main__":
    unittest.main()


def test_service_key_is_accepted_only_on_internal_text_indexing_routes(client: TestClient):
    key, identifier, digest = generate_api_key()
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        service_id = connection.execute(
            "INSERT INTO users(name,external_id,account_type) VALUES ('Indexer','test-indexer','service') RETURNING id"
        ).fetchone()[0]
        role_id = connection.execute(
            "SELECT id FROM roles WHERE code='text-indexer-service'"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO user_role_assignments(user_id,role_id) VALUES (%s,%s)",
            (service_id, role_id),
        )
        connection.execute(
            """INSERT INTO service_account_credentials(
                   service_user_id,name,credential_identifier,secret_hash,expires_at
               ) VALUES (%s,'Test key',%s,%s,CURRENT_TIMESTAMP+interval '1 day')""",
            (service_id, identifier, digest),
        )
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    service_headers = {"Authorization": f"Bearer {key}", "X-Worker-ID": "test-worker"}
    assert client.get("/api/v1/internal/text-indexing/not-yet-implemented", headers=service_headers).status_code == 404
    assert client.get("/api/v1/users", headers=service_headers).status_code == 401
    assert client.get(
        "/api/v1/internal/text-indexing/not-yet-implemented",
        headers={"Authorization": "Bearer wti_invalid"},
    ).status_code == 401


def test_person_session_is_rejected_on_internal_text_indexing_routes(client: TestClient):
    assert client.get("/api/v1/internal/text-indexing/not-yet-implemented").status_code == 401
