"""Bounded current-user suggestions for the Audit Trail actor filter."""
from psycopg import sql


def actor_suggestions(connection, query, *, limit=25, entity_type=None, actor_type=None):
    """Suggest current users only; historical text matching belongs to Apply.

    Legacy event scopes are accepted for compatibility but cannot constrain a
    directory lookup. This read never queries or authorizes event-history rows.
    """
    term = query.strip()
    if len(term) < 2:
        return {"items": [], "has_more": False}
    pattern = '%' + term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    query_sql = sql.SQL("""
        SELECT id AS actor_user_id, name AS actor_name, email AS actor_email,
               'user'::text AS actor_type
        FROM users
        WHERE name ILIKE %s ESCAPE '\\' OR email ILIKE %s ESCAPE '\\'
        ORDER BY lower(name) NULLS LAST, lower(email) NULLS LAST, id
        LIMIT %s
    """)
    items = list(connection.execute(query_sql, [pattern, pattern, limit + 1]).fetchall())
    return {"items": items[:limit], "has_more": len(items) > limit}
