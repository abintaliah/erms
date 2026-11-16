"""Canonical internal envelope insert for human, amendment, and system sends.

Only the messaging services call this writer, after their respective policy and
content checks. PostgreSQL enforces the immutable envelope shape. Callers own
the transaction and invoke the shared fan_out writer before committing.
"""

from psycopg import sql


def insert_envelope(connection, fields, *, retention_days=None):
    from .config import LIMITS
    fields = dict(fields, expiry_restoration_days=LIMITS['DELETION_RECOVERY_DAYS'])
    columns = list(fields)
    expressions = [sql.Placeholder() for _ in columns]
    parameters = list(fields.values())
    if retention_days is not None:
        if "expires_at" in fields:
            raise ValueError("Specify an expiry or a retention duration, not both")
        columns.append("expires_at")
        expressions.append(sql.SQL("CURRENT_TIMESTAMP+make_interval(days=>%s)"))
        parameters.append(retention_days)
    connection.execute(
        sql.SQL("INSERT INTO message_envelopes ({}) VALUES ({})").format(
            sql.SQL(",").join(map(sql.Identifier, columns)),
            sql.SQL(",").join(expressions),
        ),
        parameters,
    )
