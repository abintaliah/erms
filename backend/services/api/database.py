from collections.abc import Generator

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .audit_context import (
    actor_type_context,
    actor_user_id_context,
    change_reason_context,
    correlation_id_context,
    event_metadata_context,
    event_source_context,
    request_id_context,
)
from .config import float_environment, integer_environment, required_environment


def database_url() -> str:
    return required_environment("DATABASE_URL")


POOL_TIMEOUT = float_environment("DB_POOL_TIMEOUT", 10, minimum=0.1)

pool = ConnectionPool(
    conninfo=database_url(),
    min_size=integer_environment("DB_POOL_MIN_SIZE", 1, minimum=0),
    max_size=integer_environment("DB_POOL_MAX_SIZE", 10, minimum=1),
    timeout=POOL_TIMEOUT,
    kwargs={"row_factory": dict_row},
    name="erms-api",
    open=False,
)


def open_pool() -> None:
    pool.open(wait=True, timeout=POOL_TIMEOUT)


def close_pool() -> None:
    pool.close()


def get_connection() -> Generator[Connection, None, None]:
    with pool.connection() as connection:
        connection.execute(
            """
            SELECT
                set_config('app.user_id', %s, true),
                set_config('app.actor_type', %s, true),
                set_config('app.event_source', %s, true),
                set_config('app.request_id', %s, true),
                set_config('app.correlation_id', %s, true),
                set_config('app.change_reason', %s, true),
                set_config('app.event_metadata', %s, true)
            """,
            (
                actor_user_id_context.get(),
                actor_type_context.get(),
                event_source_context.get(),
                request_id_context.get(),
                correlation_id_context.get(),
                change_reason_context.get(),
                event_metadata_context.get(),
            ),
        )
        yield connection
