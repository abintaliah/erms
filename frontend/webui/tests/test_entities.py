from io import BytesIO
import inspect
from types import SimpleNamespace

import pytest

from frontend.webui.app import (
    AGGREGATION_SUMMARY_LAYOUT_CLASSES,
    CHILD_AGGREGATION_CLASSIFICATION_HELP,
    CLASSIFICATION_WORKSPACE_SEARCH_FIELDS,
    CLASSIFICATION_SELECTOR_SEARCH_FIELDS,
    RECORD_UPLOAD_WAIT_MESSAGE,
    RECORD_DETAIL_HEADER_CLASSES,
    RECORD_DETAIL_TITLE_CLASSES,
    LIFECYCLE_ACTION_BUTTONS,
    NAVIGATION_TRAIL_LIMIT,
    NAVIGATION_VISIBLE_LIMIT,
    USER_SUSPENSION_ACTION_BUTTONS,
    STOP_PROPAGATION_CLICK_HANDLER,
    buffer_upload_batch,
    component_uploader,
    component_file_icon,
    decorate_relationship_rows,
    display_value,
    format_file_size,
    form_payload,
    format_timestamp,
    filter_membership_rows,
    index,
    user_avatar,
    relationship_options,
    append_navigation_entry,
    visible_navigation_indices,
)
from frontend.webui.app import native_preview_kind
from frontend.webui.entities import ENTITIES
from frontend.webui.config import (
    classification_recent_selection_limit,
    dashboard_favourite_item_limit,
    dashboard_recent_days,
    dashboard_recent_item_limit,
    user_details_session_limit,
)
from frontend.webui.app import favourite_preview


def test_native_preview_kind_uses_safe_browser_renderers():
    assert native_preview_kind("image/png") == "image"
    assert native_preview_kind("audio/mpeg") == "audio"
    assert native_preview_kind("video/mp4") == "video"
    assert native_preview_kind("image/svg+xml") is None
    assert native_preview_kind("application/pdf") is None


class Control:
    def __init__(self, value):
        self.value = value


def test_first_class_navigation_excludes_digital_components():
    assert tuple(ENTITIES) == (
        "aggregations", "records", "classification-schemes", "classifications",
        "org-units", "users", "roles",
    )
    assert ENTITIES["aggregations"].search_first
    assert ENTITIES["records"].search_first
    assert ENTITIES["org-units"].fields[0].lookup_resource == "org-units"
    assert ENTITIES["roles"].fields[0].lookup_resource == "org-units"
    assert ENTITIES["roles"].fields[1].lookup_resource == "roles"


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


def test_relationship_options_prioritize_name_over_internal_id():
    options = relationship_options(
        [{"id": 42, "code": "RM", "name": "Records Management"}],
        ("code", "name"),
    )
    assert options == {42: "RM · Records Management"}


def test_relationship_columns_replace_foreign_keys_with_business_labels():
    units = [
        {"id": 1, "code": "HQ", "name": "Headquarters", "parent_org_unit_id": None},
        {"id": 2, "code": "RM", "name": "Records", "parent_org_unit_id": 1},
    ]
    decorated_units = decorate_relationship_rows("org-units", units)
    assert decorated_units[1]["parent_org_unit_display"] == {
        "name": "Headquarters", "code": "HQ"
    }

    roles = [{"id": 8, "org_unit_id": 2, "code": "DIR", "name": "Director"}]
    decorated_roles = decorate_relationship_rows("roles", roles, units)
    assert decorated_roles[0]["org_unit_display"] == {
        "name": "Records", "code": "RM"
    }


def test_timestamp_formatter_is_human_readable():
    formatted = format_timestamp("2026-09-15T08:05:00+00:00")
    assert "2026" in formatted
    assert "T08:05:00" not in formatted
    assert format_timestamp(None) == "—"


def test_plain_metadata_containing_uppercase_t_is_not_treated_as_a_timestamp():
    code = "CORPORATE-RECORDS-MANAGEMENT-SCHEME-2026"
    description = "This description must remain complete."
    assert display_value(code) == code
    assert display_value(description) == description
    assert display_value(None) == "—"


def test_dashboard_recent_configuration(monkeypatch):
    monkeypatch.setenv("DASHBOARD_RECENT_ITEM_LIMIT", "7")
    monkeypatch.setenv("DASHBOARD_RECENT_DAYS", "14")
    assert dashboard_recent_item_limit() == 7
    assert dashboard_recent_days() == 14


def test_dashboard_favourite_configuration_and_preview(monkeypatch):
    monkeypatch.setenv("DASHBOARD_FAVOURITE_ITEM_LIMIT", "2")
    assert dashboard_favourite_item_limit() == 2
    items = [{"id": 1}, {"id": 2}, {"id": 3}]
    assert favourite_preview(items, 2) == (items[:2], True)
    assert favourite_preview(items[:2], 2) == (items[:2], False)


def test_dashboard_favourite_configuration_defaults_to_five(monkeypatch):
    monkeypatch.delenv("DASHBOARD_FAVOURITE_ITEM_LIMIT", raising=False)
    assert dashboard_favourite_item_limit() == 5


def test_user_details_session_limit_defaults_to_five_and_is_configurable(monkeypatch):
    monkeypatch.delenv("USER_DETAILS_SESSION_LIMIT", raising=False)
    assert user_details_session_limit() == 5
    monkeypatch.setenv("USER_DETAILS_SESSION_LIMIT", "8")
    assert user_details_session_limit() == 8


def test_membership_filters_identity_status_and_overlapping_validity():
    rows = [
        {
            "id": 1, "counterpart_search": "Alya Al-Salman alya@example.test",
            "counterpart_status": "active", "valid_from": "2026-01-01T00:00:00Z",
            "valid_until": None,
        },
        {
            "id": 2, "counterpart_search": "Sami Jari sami@example.test",
            "counterpart_status": "suspended", "valid_from": "2025-01-01T00:00:00Z",
            "valid_until": "2025-12-31T23:59:59Z",
        },
    ]
    assert [row["id"] for row in filter_membership_rows(rows, query="alya")] == [1]
    assert [row["id"] for row in filter_membership_rows(rows, query="SAMI@EXAMPLE")] == [2]
    assert [row["id"] for row in filter_membership_rows(rows, status="suspended")] == [2]
    assert [row["id"] for row in filter_membership_rows(
        rows, valid_from="2026-06-01", valid_until="2026-06-30",
    )] == [1]


def test_user_avatar_is_stable_and_uses_best_effort_initials():
    user = {"id": 42, "name": "Sami Mali Jibtou Jari", "email": "sami@example.test"}
    first = user_avatar(user)
    assert first["initials"] == "SJ"
    assert first == user_avatar(user)
    assert user_avatar({"id": 43, "name": "Admin"})["initials"] == "AD"
    assert user_avatar({"id": 44, "name": ""})["initials"] == "?"


def test_classification_recent_selection_configuration(monkeypatch):
    monkeypatch.setenv("CLASSIFICATION_RECENT_SELECTION_LIMIT", "6")
    assert classification_recent_selection_limit() == 6


def test_classification_workspace_search_includes_keywords():
    assert CLASSIFICATION_WORKSPACE_SEARCH_FIELDS == (
        "code", "title", "description", "keywords",
    )
    assert CLASSIFICATION_SELECTOR_SEARCH_FIELDS == (
        "code", "title", "description", "keywords",
    )
    assert ENTITIES["classifications"].search_fields == (
        "code", "title", "description", "keywords",
    )


def test_contextual_form_help_explains_disabled_controls():
    assert "inherit classification governance" in CHILD_AGGREGATION_CLASSIFICATION_HELP
    assert "cannot have a classification assigned directly" in CHILD_AGGREGATION_CLASSIFICATION_HELP
    assert RECORD_UPLOAD_WAIT_MESSAGE == "Please wait until all files have finished uploading."


def test_aggregation_summary_has_non_collapsing_flex_layout():
    assert "flex-1" in AGGREGATION_SUMMARY_LAYOUT_CLASSES
    assert "min-w-[360px]" in AGGREGATION_SUMMARY_LAYOUT_CLASSES


def test_record_detail_header_keeps_controls_visible_beside_long_titles():
    assert "no-wrap" in RECORD_DETAIL_HEADER_CLASSES
    assert "grow" in RECORD_DETAIL_TITLE_CLASSES
    assert "min-w-0" in RECORD_DETAIL_TITLE_CLASSES


def test_record_detail_aggregation_navigation_uses_click_handler_not_route_link():
    source = inspect.getsource(index)
    assert "on_click=open_containing_aggregation" in source
    assert "ui.link(aggregation_label, target=open_containing_aggregation)" not in source


def test_detail_page_editors_resolve_api_entity_resources_explicitly():
    source = inspect.getsource(index)
    assert 'record, on_saved=refresh_record_view, resource_key="records"' in source
    assert 'current, on_saved=open_aggregation,\n                                        resource_key="aggregations"' in source
    assert '"aggregation-details": "aggregations"' in source
    assert '"record-details": "records"' in source


def test_navigation_trail_collapses_only_consecutive_duplicates_and_is_bounded():
    trail = []
    for index in range(NAVIGATION_TRAIL_LIMIT + 3):
        trail = append_navigation_entry(trail, {
            "page": "record-details", "entity_id": index, "label": f"Record {index}",
        })
    assert len(trail) == NAVIGATION_TRAIL_LIMIT
    assert trail[0]["entity_id"] == 3
    unchanged_length = append_navigation_entry(trail, {
        "page": "record-details", "entity_id": trail[-1]["entity_id"],
        "label": "Updated label",
    })
    assert len(unchanged_length) == NAVIGATION_TRAIL_LIMIT
    assert unchanged_length[-1]["label"] == "Updated label"


def test_navigation_visible_entries_retain_first_and_recent_pages():
    visible, hidden = visible_navigation_indices(9)
    assert len(visible) == NAVIGATION_VISIBLE_LIMIT
    assert visible == [0, 5, 6, 7, 8]
    assert hidden == [1, 2, 3, 4]


def test_navigation_drawer_does_not_load_or_render_entity_counts():
    source = inspect.getsource(index)
    assert "navigation_badges" not in source
    assert "refresh_navigation_counts" not in source


def test_navigation_drawer_collapses_to_clickable_icon_rail():
    source = inspect.getsource(index)
    assert '"width=300 mini-width=64 show-if-above bordered"' in source
    assert 'drawer_link("Browse", "lan")' in source
    assert "erms-nav-link" in source
    assert "white-space: nowrap" in source
    assert ".erms-nav-link:hover" in source
    assert 'drawer.props(add="mini")' in source
    assert 'drawer.props(remove="mini")' in source
    assert 'drawer.classes(add="erms-drawer--collapsed")' in source
    assert 'button.text = ""' in source
    assert 'button.classes(add="justify-center px-0"' in source
    assert "ui.tooltip(label)" in source


def test_favourite_click_handler_stops_propagation_inside_function():
    assert STOP_PROPAGATION_CLICK_HANDLER.startswith("(event) =>")
    assert "event.stopPropagation(); emit();" in STOP_PROPAGATION_CLICK_HANDLER


def test_lifecycle_actions_keep_activate_button_for_inactive_rows():
    assert 'v-if="props.row.status === \'inactive\'"' in LIFECYCLE_ACTION_BUTTONS
    assert 'icon="toggle_on"' in LIFECYCLE_ACTION_BUTTONS
    assert 'aria-label="Activate"' in LIFECYCLE_ACTION_BUTTONS
    assert "v-else" in LIFECYCLE_ACTION_BUTTONS
    assert 'aria-label="Deactivate"' in LIFECYCLE_ACTION_BUTTONS


def test_suspend_action_remains_visible_but_disabled_for_inactive_users():
    assert 'v-if="props.row.status !== \'suspended\'"' in USER_SUSPENSION_ACTION_BUTTONS
    assert ':disable="props.row.status !== \'active\'"' in USER_SUSPENSION_ACTION_BUTTONS
    assert "Activate the user before suspending" in USER_SUSPENSION_ACTION_BUTTONS
    assert 'icon="play_circle"' in USER_SUSPENSION_ACTION_BUTTONS


def test_dashboard_recent_configuration_rejects_non_positive_values(monkeypatch):
    monkeypatch.setenv("DASHBOARD_RECENT_ITEM_LIMIT", "0")
    with pytest.raises(RuntimeError, match="must be at least 1"):
        dashboard_recent_item_limit()

    monkeypatch.setenv("DASHBOARD_FAVOURITE_ITEM_LIMIT", "0")
    with pytest.raises(RuntimeError, match="must be at least 1"):
        dashboard_favourite_item_limit()


def test_component_display_helpers_prioritize_readable_file_information():
    assert format_file_size(512) == "512 B"
    assert format_file_size(1_572_864) == "1.5 MB"
    assert format_file_size(None) == "—"
    assert component_file_icon("application/pdf") == "picture_as_pdf"
    assert component_file_icon("image/jpeg") == "image"
    assert component_file_icon("application/octet-stream") == "draft"


def test_component_uploader_batches_multiple_files_into_one_handler():
    uploader = component_uploader(lambda event: None)
    assert uploader._props["multiple"] is True
    assert uploader._props["batch"] is True
    assert uploader._upload_handlers == []
    assert len(uploader._multi_upload_handlers) == 1
    assert "list" in uploader.slots
    assert "file.__img" not in uploader.slots["list"].template
    assert "file.__sizeLabel" in uploader.slots["list"].template


def test_upload_batch_is_fully_buffered_before_api_awaits():
    sources = [BytesIO(b"first"), BytesIO(b"second"), BytesIO(b"third")]
    event = SimpleNamespace(
        contents=sources,
        names=["one.txt", "two.txt", "three.txt"],
        types=["text/plain", "text/plain", ""],
    )
    assert buffer_upload_batch(event) == [
        (b"first", "one.txt", "text/plain"),
        (b"second", "two.txt", "text/plain"),
        (b"third", "three.txt", "application/octet-stream"),
    ]
    assert all(source.tell() > 0 for source in sources)
