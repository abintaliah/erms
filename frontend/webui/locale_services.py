"""Shared WebUI locale/timezone primitives used by all future screens."""
from __future__ import annotations

from contextvars import ContextVar
from collections import Counter
from datetime import date, datetime, timezone
import logging
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from nicegui import context


_active_locale: ContextVar[tuple[str, str] | None] = ContextVar(
    "wathiq_active_locale", default=None,
)
_client_locales: dict[str, tuple[str, str]] = {}
_ENGLISH_MONTHS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_ARABIC_MONTHS = ("", "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر")
_locale_metrics: Counter[str] = Counter()
logger = logging.getLogger(__name__)


class LocalizedTimezoneError(ValueError):
    def __init__(self, message_key: str, **parameters: str):
        self.message_key = message_key
        self.parameters = parameters
        super().__init__(message_key)


def locale_metrics() -> dict[str, int]:
    return dict(_locale_metrics)


def _timezone_failure(reason: str, timezone_name: str) -> None:
    _locale_metrics[reason] += 1
    logger.warning(
        "timezone_resolution_failed",
        extra={"reason": reason, "timezone_name": timezone_name},
    )


def set_locale_context(language_tag: str, timezone_name: str) -> None:
    value = (language_tag, working_zone(timezone_name).key)
    _active_locale.set(value)
    try:
        _client_locales[context.client.id] = value
    except RuntimeError:
        pass


def clear_locale_context(client_id: str) -> None:
    _client_locales.pop(client_id, None)


def current_locale_context() -> tuple[str, str]:
    try:
        value = _client_locales.get(context.client.id, _active_locale.get())
    except RuntimeError:
        value = _active_locale.get()
    if value is None:
        raise RuntimeError("locale context must be initialized before formatting user values")
    return value


def working_zone(timezone_name: str) -> ZoneInfo:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exception:
        _timezone_failure("invalid_timezone", timezone_name)
        raise ValueError("unknown IANA timezone") from exception
    if zone.key != timezone_name:
        raise ValueError("timezone must use its canonical IANA identifier")
    return zone


def utc_instant_to_working(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        _timezone_failure("offset_free_instant", timezone_name)
        raise ValueError("stored instants must include a UTC offset")
    return value.astimezone(working_zone(timezone_name))


def working_datetime_to_utc(
    value: datetime, timezone_name: str,
    ambiguity: Literal["earlier", "later"] | None = None,
) -> datetime:
    """Interpret a wall time in the working zone and reject gaps/ambiguities."""
    if value.tzinfo is not None:
        raise ValueError("working datetime input must not contain an offset")
    zone = working_zone(timezone_name)
    candidates = []
    for fold in (0, 1):
        candidate = value.replace(tzinfo=zone, fold=fold)
        if candidate.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == value:
            candidates.append(candidate)
    offsets = {candidate.utcoffset() for candidate in candidates}
    if not candidates:
        _timezone_failure("nonexistent_wall_time", timezone_name)
        raise LocalizedTimezoneError(
            "timezone.validation.wall_time.nonexistent",
            local_time=value.isoformat(timespec="minutes"), timezone=timezone_name,
        )
    if len(offsets) > 1:
        if ambiguity is None:
            _timezone_failure("ambiguous_wall_time", timezone_name)
            raise LocalizedTimezoneError(
                "timezone.validation.wall_time.ambiguous",
                local_time=value.isoformat(timespec="minutes"), timezone=timezone_name,
            )
        ordered = sorted(candidates, key=lambda item: item.astimezone(timezone.utc))
        return ordered[0 if ambiguity == "earlier" else -1].astimezone(timezone.utc)
    return candidates[0].astimezone(timezone.utc)


def date_value(value: date) -> str:
    """Dates are calendar values and never receive timezone conversion."""
    return value.isoformat()


def format_instant(value: datetime | str, timezone_name: str, language_tag: str) -> str:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    local = utc_instant_to_working(parsed, timezone_name)
    months = _ARABIC_MONTHS if language_tag.lower().split("-", 1)[0] == "ar" else _ENGLISH_MONTHS
    hour = local.hour % 12 or 12
    period = ("ص" if local.hour < 12 else "م") if months is _ARABIC_MONTHS else ("AM" if local.hour < 12 else "PM")
    return f"{local.day} {months[local.month]} {local.year}, {hour:02d}:{local.minute:02d} {period}"


def format_local_date(value: date | str, language_tag: str) -> str:
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        # Calendar-date fields occasionally arrive serialized as an ISO
        # datetime by older API/database paths. Preserve the stored calendar
        # date; do not apply a timezone conversion to a date-only value.
        parsed = date.fromisoformat(str(value).strip()[:10])
    months = _ARABIC_MONTHS if language_tag.lower().split("-", 1)[0] == "ar" else _ENGLISH_MONTHS
    return f"{parsed.day} {months[parsed.month]} {parsed.year}"
