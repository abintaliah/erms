from collections.abc import Generator

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

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
        yield connection
