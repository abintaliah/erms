"""Commit before returning a result; retry the entire consistent-snapshot operation."""

from psycopg.errors import DeadlockDetected, SerializationFailure, UniqueViolation
from ..database import pool
from .content import invalid


def run(user_id, operation):
    for attempt in range(8):
        try:
            with pool.connection() as connection:
                with connection.transaction():
                    connection.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    connection.execute(
                        "SELECT set_config('app.user_id',%s,true)", (str(user_id),)
                    )
                    result = operation(connection)
            return result
        except (SerializationFailure, DeadlockDetected):
            if attempt == 7:
                invalid("message_retry_required", 409)
        except UniqueViolation as error:
            # A concurrent request may have committed after our MVCC snapshot.
            if error.diag.constraint_name not in {
                "message_envelopes_user_request_idx",
                "message_request_receipts_user_key",
                "message_action_amendments_original_envelope_id_sequence_key",
                "message_action_amendments_created_by_user_id_request_id_key",
                "message_action_completions_pkey",
                "message_envelopes_system_request_idx",
                "message_envelopes_system_event_idx",
                "message_request_receipts_producer_key",
                "message_request_receipts_event_key",
            }:
                raise
            if attempt == 7:
                invalid("message_retry_required", 409)
