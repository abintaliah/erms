from pydantic import ValidationError
import pytest

from backend.services.api.schemas import AggregationCreate, RecordCreate


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            AggregationCreate,
            {
                "aggregation_number": "AG-1",
                "title": "Test aggregation",
                "date_opened": "2026-01-15T09:30:00",
            },
        ),
        (
            RecordCreate,
            {
                "aggregation_id": 1,
                "record_number": "REC-1",
                "title": "Test record",
                "date_originated": "2026-01-15T09:30:00",
            },
        ),
    ],
)
def test_instant_inputs_reject_offset_free_datetimes(model, payload):
    with pytest.raises(ValidationError, match="timezone"):
        model.model_validate(payload)


def test_instant_inputs_accept_utc_and_explicit_offsets():
    utc_value = AggregationCreate.model_validate(
        {
            "aggregation_number": "AG-1",
            "title": "Test aggregation",
            "date_opened": "2026-01-15T09:30:00Z",
        }
    )
    offset_value = RecordCreate.model_validate(
        {
            "aggregation_id": 1,
            "record_number": "REC-1",
            "title": "Test record",
            "date_originated": "2026-01-15T09:30:00+04:00",
        }
    )

    assert utc_value.date_opened is not None
    assert utc_value.date_opened.utcoffset() is not None
    assert offset_value.date_originated is not None
    assert offset_value.date_originated.utcoffset() is not None
