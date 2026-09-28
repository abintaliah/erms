from contextvars import ContextVar


request_id_context: ContextVar[str] = ContextVar("request_id", default="")
correlation_id_context: ContextVar[str] = ContextVar("correlation_id", default="")
actor_user_id_context: ContextVar[str] = ContextVar("actor_user_id", default="")
actor_name_context: ContextVar[str] = ContextVar("actor_name", default="")
actor_email_context: ContextVar[str] = ContextVar("actor_email", default="")
actor_type_context: ContextVar[str] = ContextVar("actor_type", default="anonymous")
event_source_context: ContextVar[str] = ContextVar("event_source", default="api")
change_reason_context: ContextVar[str] = ContextVar("change_reason", default="")
event_metadata_context: ContextVar[str] = ContextVar("event_metadata", default="{}")


def decode_change_reason(value: str | None) -> str:
    """Decode UTF-8 header bytes exposed by ASGI as Latin-1 text.

    ASCII is unchanged; non-UTF-8 input falls back to Latin-1. Call this
    only at the header boundary, not on JSON bodies or already-decoded reasons.
    """
    if value is None:
        return ""
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
