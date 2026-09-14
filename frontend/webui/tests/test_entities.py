import pytest

from frontend.webui.app import form_payload
from frontend.webui.entities import ENTITIES


class Control:
    def __init__(self, value):
        self.value = value


def test_first_class_navigation_excludes_digital_components():
    assert tuple(ENTITIES) == ("aggregations", "records", "org-units", "users", "roles")
    assert ENTITIES["aggregations"].search_first
    assert ENTITIES["records"].search_first


def test_form_payload_converts_ids_and_omits_empty_create_fields():
    spec = ENTITIES["records"]
    controls = {
        "aggregation_id": Control(12.0),
        "record_number": Control(" REC-12 "),
        "title": Control("Annual report"),
        "description": Control(""),
        "date_originated": Control(""),
    }
    assert form_payload(spec, controls, creating=True) == {
        "aggregation_id": 12,
        "record_number": "REC-12",
        "title": "Annual report",
    }


def test_form_payload_rejects_required_blank_value():
    spec = ENTITIES["users"]
    controls = {"name": Control("  "), "email": Control(""), "external_id": Control("")}
    with pytest.raises(ValueError, match="Name is required"):
        form_payload(spec, controls, creating=True)
