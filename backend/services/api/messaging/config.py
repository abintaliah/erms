"""Restart-scoped, validated deployment limits (specification section 11.5)."""

from ..config import integer_environment

DEFAULTS = {
    "MAX_SELECTORS_PER_SEND": 100,
    "MAX_RECIPIENTS_PER_SEND": 2000,
    "MAX_RESOURCE_LINKS": 50,
    "DRAFT_ACTIVE_DAYS": 180,
    "DRAFT_WARNING_DAYS": 30,
    "DRAFT_RECOVERY_DAYS": 30,
    "CAPTURE_MAX_LINKED_MESSAGES": 100,
    "CAPTURE_MAX_PDF_BYTES": 52428800,
    "RETENTION_DAYS": 1095,
    "RETENTION_WARNING_DAYS": 90,
    "DELETION_RECOVERY_DAYS": 30,
    "CLEANUP_INTERVAL_SECONDS": 3600,
    "CLEANUP_BATCH_SIZE": 500,
    "TEST_MAX_RECIPIENTS": 10,
    "TEST_SENDS_PER_HOUR": 20,
    "TEST_RETENTION_DAYS": 30,
}
LIMITS = {
    name: integer_environment("MESSAGING_" + name, value, minimum=1)
    for name, value in DEFAULTS.items()
}
for prefix in ("DRAFT", "RETENTION"):
    active = (
        LIMITS["DRAFT_ACTIVE_DAYS"] if prefix == "DRAFT" else LIMITS["RETENTION_DAYS"]
    )
    if LIMITS[prefix + "_WARNING_DAYS"] >= active:
        raise RuntimeError(
            f"MESSAGING_{prefix}_WARNING_DAYS must be less than its active period"
        )
if LIMITS["TEST_MAX_RECIPIENTS"] > LIMITS["MAX_RECIPIENTS_PER_SEND"]:
    raise RuntimeError("MESSAGING_TEST_MAX_RECIPIENTS exceeds the send recipient limit")
# Bound datetime arithmetic, SQL bigint sequence values, and request allocations.
for name, value in LIMITS.items():
    if value > (36500 if name.endswith("_DAYS") else 2147483647):
        raise RuntimeError(f"MESSAGING_{name} exceeds the supported safe range")
