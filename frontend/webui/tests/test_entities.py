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
    RELATIONSHIP_DISPLAY_FIELDS,
    LIFECYCLE_ACTION_BUTTONS,
    LAST_CUSTODIAN_MESSAGE,
    LAST_CUSTODIAN_TITLE,
    NAVIGATION_TRAIL_LIMIT,
    NAVIGATION_VISIBLE_LIMIT,
    USER_SUSPENSION_ACTION_BUTTONS,
    STOP_PROPAGATION_CLICK_HANDLER,
    apply_relationship_selection,
    buffer_upload_batch,
    component_uploader,
    component_file_icon,
    decorate_relationship_rows,
    deletion_blocked_report,
    deletion_identity,
    display_value,
    error_message,
    show_api_error,
    field_input,
    format_file_size,
    form_payload,
    format_timestamp,
    filter_membership_rows,
    index,
    medium_label,
    user_avatar,
    relationship_options,
    role_change_requires_reason,
    append_navigation_entry,
    visible_navigation_indices,
)
from frontend.webui.api_client import ApiError
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

APP_SOURCE = inspect.getsource(index)


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
        "org-units", "users", "roles", "security-levels", "profiles", "privileges",
        "permissions",
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
        "date_of_next_review": Control(""),
        "security_level_id": Control(1.0),
        "medium": Control("mixed"),
    }
    assert form_payload(spec, controls, creating=True) == {
        "aggregation_id": 12,
        "record_number": "REC-12",
        "title": "Annual report",
        "security_level_id": 1,
        "medium": "mixed",
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


def test_medium_label_uses_accessible_business_terms():
    assert medium_label("digital") == "Digital"
    assert medium_label("physical") == "Physical"
    assert medium_label("mixed") == "Mixed"
    assert medium_label(None) == "—"


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


def test_aggregation_summary_has_command_centre_layout():
    assert "flex-1" in AGGREGATION_SUMMARY_LAYOUT_CLASSES
    assert "aggregation-command-summary" in AGGREGATION_SUMMARY_LAYOUT_CLASSES
    assert "min-w-[520px]" in AGGREGATION_SUMMARY_LAYOUT_CLASSES


def test_record_detail_header_wraps_actions_before_crowding_long_titles():
    assert "flex-wrap" in RECORD_DETAIL_HEADER_CLASSES
    assert "no-wrap" not in RECORD_DETAIL_HEADER_CLASSES
    assert "flex-1" in RECORD_DETAIL_TITLE_CLASSES
    assert "sm:min-w-[420px]" in RECORD_DETAIL_TITLE_CLASSES
    assert "max-w-full" in RECORD_DETAIL_TITLE_CLASSES
    assert "basis-[520px]" in RECORD_DETAIL_TITLE_CLASSES


def test_scalar_display_columns_are_not_rendered_as_relationship_links():
    assert RELATIONSHIP_DISPLAY_FIELDS == {
        "aggregation_display",
        "org_unit_display",
        "parent_org_unit_display",
        "profile_display",
        "scheme_display",
    }
    scalar_fields = {
        "medium_display", "vital_display", "review_display", "location_display",
    }
    assert scalar_fields.isdisjoint(RELATIONSHIP_DISPLAY_FIELDS)
    assert "if key not in RELATIONSHIP_DISPLAY_FIELDS:" in APP_SOURCE


def test_record_and_aggregation_scalar_columns_remain_plain_text():
    for resource in ("records", "aggregations"):
        displayed_fields = {
            key for key, _ in ENTITIES[resource].columns if key.endswith("_display")
        }
        assert {
            "medium_display", "vital_display", "review_display", "location_display",
        } <= displayed_fields
        assert (
            displayed_fields - {"aggregation_display"}
        ).isdisjoint(RELATIONSHIP_DISPLAY_FIELDS)


def test_governed_collection_rows_open_details_instead_of_direct_editors():
    collection_actions = APP_SOURCE[
        APP_SOURCE.index('if spec.key in {"records", "aggregations"}:'):
        APP_SOURCE.index('elif spec.key in {"privileges", "permissions"}:')
    ]
    assert "$parent.$emit(\\'edit\\', props.row)" not in collection_actions
    assert 'icon="open_in_new"' in APP_SOURCE
    assert "$parent.$emit(\\'open_record\\', props.row)" in APP_SOURCE
    assert 'table.on("open_record", lambda event: show_record_details(event.args))' in APP_SOURCE


def test_governed_metadata_editor_fails_closed_without_modify_capability():
    editor = APP_SOURCE[
        APP_SOURCE.index("async def open_editor("):
        APP_SOURCE.index("async def show_memberships(")
    ]
    capability_check = editor.index(
        'editor_capabilities = await api.resource_capabilities('
    )
    denial_check = editor.index(
        'if not editor_capabilities.get("modify_metadata"):'
    )
    dialog_open = editor.index("dialog.open()")
    assert capability_check < denial_check < dialog_open
    assert "Your effective roles do not allow editing this" in editor


def test_detail_pages_use_light_blue_metadata_and_retention_visual_system():
    source = inspect.getsource(index)
    assert 'primary="#268bd2"' in source
    assert ".detail-field-label" in source
    assert ".retention-card" in source
    assert '("Current",' in source
    assert '("Intermediate",' in source
    assert '("Final",' in source
    assert 'ui.label(str(len(children))).classes("text-2xl font-bold text-primary")' not in source
    assert '"retention-card aggregation-retention-compact shadow-none p-4 gap-3"' in source


def test_application_shell_is_flat_and_uses_one_background():
    source = inspect.getsource(index)
    assert "with ui.header().classes" in source
    assert "ui.header(elevated=True)" not in source
    assert "background: var(--erms-bg); color: var(--erms-ink);" in source
    assert ".erms-content .q-card { box-shadow: none !important; }" in source
    assert 'ui.image("/static/brand/wathiq-mark.svg?v=2")' in source
    assert 'ui.label("wathiq").classes("erms-brand-name")' in source
    assert 'ui.label("ERMS")' not in source
    assert "family=Righteous&display=swap" in source
    assert "font-family: Righteous, Inter" in source
    assert "letter-spacing: .035em" in source
    assert ".erms-page-table" in source
    assert ".erms-page-table .q-table thead tr { background: #eef7fd; }" in source
    assert ".erms-page-table .q-table tbody td" in source
    assert 'classes("erms-page-table")' in source
    assert ".login-sessions-table .q-table th" in source
    assert "white-space: nowrap" in source
    assert '"label": "Signed in", "field": "date_created", "align": "left", "sortable": True' in source
    assert 'label="Force sign-out"' in source
    assert 'ui.row().classes("w-full items-center no-wrap gap-4")' in source
    assert 'ui.row().classes("items-center no-wrap gap-2 flex-none")' in source
    assert 'ui.label("Search results").classes("text-lg font-semibold")' in source
    assert '"Filter displayed results"' in source
    assert 'table.bind_filter_from(result_filter, "value")' in source
    assert 'sortable_relationships = {"parent_org_unit_display", "org_unit_display", "profile_display"}' in source
    assert 'not key.endswith("_display") or key in sortable_relationships' in source
    assert '"Search code, name, or parent unit"' in source
    assert '"Search code, name, or organization unit"' in source
    assert '"Search name or email"' in source
    assert '"All account types"' in source
    assert '"w-full items-center gap-3 px-5 pt-2 pb-1 mb-2"' in source
    assert ':rows-per-page-options="[10,25,50,100]"' in source
    assert '"Filter records"' in source
    assert 'record_table.bind_filter_from(contained_record_filter, "value")' in source


def test_brand_assets_are_exposed_through_the_frontend_static_route():
    module_source = inspect.getsource(inspect.getmodule(index))
    assert 'app.add_static_files("/static/brand"' in module_source
    assert 'title="wathiq"' in module_source
    assert 'favicon=Path(__file__).with_name("static") / "brand" / "wathiq-mark.svg"' in module_source


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
    assert "active_count" not in source
    assert "sum(row.get('status') == 'active' for row in rows)" in source


def test_navigation_drawer_collapses_to_clickable_icon_rail():
    source = inspect.getsource(index)
    assert '"width=300 mini-width=64 show-if-above"' in source
    assert '"width=300 mini-width=64 show-if-above bordered"' not in source
    assert '"Browse", "lan", navigation_key="organization-browser"' in source
    assert "erms-nav-link" in source
    assert "white-space: nowrap" in source
    assert ".erms-nav-link:hover" in source
    assert ".erms-nav-heading" in source
    assert ".erms-nav-link--active" in source
    assert "background: #ffffff; color: #172033;" in source
    assert "--erms-bg: #ffffff" in source
    assert "color: #1f2937 !important" in source
    assert 'font-family: "Material Symbols Outlined" !important' in source
    assert 'font-variation-settings: "FILL" 0' in source
    assert '"wght" 300' in source
    assert "background: #fff4d7 !important; color: #174b72 !important;" in source
    assert "def set_active_drawer_link(page: str)" in source
    assert 'button.props(add="aria-current=page")' in source


def test_navigation_links_scroll_independently_when_the_drawer_is_taller_than_the_viewport():
    source = inspect.getsource(index)
    assert 'ui.column().classes("erms-nav-scroll w-full gap-0 no-wrap")' in source
    assert ".erms-nav-scroll" in source
    assert "height: 100%; overflow-y: auto; overflow-x: hidden;" in source


def test_empty_navigation_sections_are_hidden_with_their_links():
    source = inspect.getsource(index)
    assert "drawer_sections: list[tuple[Any, tuple[str, ...]]]" in source
    assert "any(link_visibility.get(key, False) for key in section_keys)" in source
    assert "refresh_drawer_visibility(privileges)" in source
    assert "not drawer_collapsed" in source


def test_governance_custody_page_explains_qualification_and_empty_configuration():
    source = inspect.getsource(index)
    assert "Checks that someone can always manage and recover access to protected records" in source
    assert "At least one active person must be able to manage information" in source
    assert "Governance role enabled" in source
    assert "Highest clearance held" in source
    assert "Required profile privileges" in source
    assert "Current role assignment" in source
    assert "No information-governance roles are configured" in source
    assert "governance-overview-grid" in source
    assert "governance-metrics-row" in source
    assert "governance-empty-state" in source
    assert "Universal custodians (" in source
    assert "governance-table" in source
    assert '"person", "label": "Person"' in source
    assert 'label="Open user"' in source
    assert 'label="Open role"' in source
    assert "valid_from_display" in source
    assert "valid_until_display" in source
    assert "qualifies_for_universal_custody" in source
    assert "effective_for_universal_custody" in source
    assert "Assignments needing attention" in source
    assert "All governance-role assignments" not in source
    assert '"Current assignments"' in source
    assert "Assignments whose validity dates include the present time." in source
    assert "account, role, and organization hierarchy are active" in source
    assert "highest security clearance" in source
    assert 'pagination={"rowsPerPage": 5}' in source
    assert "def set_page_title_icon(page: str)" in source
    assert 'page_title_icon = ui.icon("dashboard")' in source
    assert "page_title_icon = ui.icon()" not in source
    assert 'ui.label("Previous sign-in")' in source
    assert 'current_user_last_login = ui.label("First sign-in")' in source
    assert 'current_user_avatar_initials = ui.label("?")' in source
    assert 'user_menu.on("show", refresh_user_profile)' in source
    assert 'my_sessions_menu' not in source
    assert '"dashboard": "dashboard"' in source
    assert '"aggregations": "folder"' in source
    assert '"records": "description"' in source
    assert '"classification-workspace": "account_tree"' in source
    assert '"org-units": "corporate_fare"' in source
    assert '"roles": "badge"' in source
    assert '"users": "group"' in source
    assert '"organization-browser": "lan"' in source
    assert '"audit-trail": "manage_history"' in source
    assert '"login-sessions": "devices"' in source
    assert '"w-full px-5 pb-5 pt-0 gap-4"' in source
    assert "background: #f4f6f8; color: var(--erms-ink);" in source
    assert "min-height: 54px; padding: 0 18px;" in source
    assert ".erms-brand-mark { width: 28px; height: 33px;" in source
    assert 'with ui.footer().classes("erms-footer items-center")' in source
    assert 'ui.label("Designed and built by Sharjah Archives")' in source
    assert ".erms-footer-credit" in source
    assert 'replace="text-positive text-lg"' in source
    assert "#popup { display: none !important; }" in source
    assert 'ui.label("wathiq").classes("wathiq-login-word")' in source
    assert 'login_submit = ui.button("Continue to wathiq"' in source
    assert 'drawer.hide()' in source
    assert 'drawer.show()' in source
    assert "Sign in to ERMS" not in source
    assert 'page_title_icon.set_visibility(False)' in source
    assert ".erms-dashboard-card .erms-shared-control" in source
    assert 'content_card.classes(add="erms-dashboard-card")' in source
    assert 'content_card.classes(remove="erms-dashboard-card")' in source
    assert 'drawer.props(add="mini")' in source
    assert 'drawer.props(remove="mini")' in source
    assert 'drawer.classes(add="erms-drawer--collapsed")' in source
    assert 'ui.button(icon="chevron_left")' in source
    assert 'icon=chevron_right' in source
    assert 'icon="menu"' not in source
    assert "erms-drawer-toggle" in source
    assert "erms-profile-action" in source
    assert 'ui.button("Change password", icon="key")' in source
    assert 'with ui.column().classes("erms-profile-actions w-full")' in source
    assert "min-height: 38px !important; height: 38px !important;" in source
    assert "gap: 0 !important" in source
    assert 'button.text = ""' in source
    assert 'button.classes(add="justify-center px-0"' in source
    assert "ui.tooltip(label)" in source


def test_forced_password_change_precedes_authenticated_data_loading():
    source = inspect.getsource(index)
    login_flow = source[
        source.index("async def submit_login()"):
        source.index('login_submit.on("click", submit_login)')
    ]
    assert login_flow.index('if principal["must_change_password"]:') < login_flow.index(
        "await reload_favourites()"
    )
    assert "Your temporary password must be replaced before you can continue." in source
    assert '"Set new password" if forced_change else "Change password"' in source
    assert '"Back to sign in", icon="arrow_back"' in source
    assert "dialog.close()\n                await sign_out()" in source


def test_structured_api_errors_prefer_the_accessible_message():
    error = ApiError(422, {
        "code": "aggregation_dates_out_of_order",
        "message": "The aggregation's closing date cannot be earlier than its opening date.",
        "technical_detail": 'new row violates check constraint "aggregations_dates_in_order"',
    })
    assert error_message(error) == (
        "The aggregation's closing date cannot be earlier than its opening date."
    )
    assert error_message(ApiError(
        422, "X-Change-Reason is required when lowering a security level",
    )) == "Please explain why the security level is being lowered, then try again."


def test_last_custodian_block_uses_a_persistent_explanatory_dialog():
    source = inspect.getsource(show_api_error)
    assert 'detail_code != "last_governance_custodian"' in source
    assert 'ui.dialog().props("persistent")' in source
    assert 'ui.button("I understand"' in source
    assert LAST_CUSTODIAN_TITLE == "This change can’t be made yet"
    assert "only active person" in LAST_CUSTODIAN_MESSAGE
    assert "No changes were saved" in LAST_CUSTODIAN_MESSAGE
    assert "Assign another active person" in LAST_CUSTODIAN_MESSAGE


def test_lowering_role_clearance_requires_the_audit_reason():
    levels = [
        {"id": 1, "level_number": 10},
        {"id": 2, "level_number": 20},
    ]
    current = {"security_level_id": 2, "profile_id": 4,
               "is_information_governance": True}
    assert role_change_requires_reason(
        current, {"security_level_id": 1}, levels,
    )
    assert not role_change_requires_reason(
        current, {"security_level_id": 2}, levels,
    )
    assert role_change_requires_reason(
        current, {"profile_id": 5}, levels,
    )


def test_permanent_deletion_uses_stable_identity_and_preserves_blocker_reports():
    assert deletion_identity({
        "id": 7, "name": "Alex Example", "email": "alex@example.test",
    }) == "Alex Example — alex@example.test"
    assert deletion_identity({
        "id": 8, "name": "Records Team", "code": "RECORDS",
    }) == "Records Team — RECORDS"
    report = {"code": "deletion_blocked", "blockers": [{"code": "self_deletion"}]}
    assert deletion_blocked_report(ApiError(409, report)) == report
    assert deletion_blocked_report(ApiError(409, "another conflict")) is None


def test_identity_detail_actions_are_explicitly_permanent():
    source = inspect.getsource(index)
    assert source.count('"Permanently delete", icon="delete_forever"') >= 3
    assert "if deletion_blocked_report(error) is not None:" in source
    assert "await confirm_identity_deletion(" in source


def test_aggregation_browser_load_more_preserves_the_previous_last_child_anchor():
    source = inspect.getsource(index)
    assert 'browse_item_dom_id(current["items"][-1])' in source
    assert "render_tree_preserving_scroll(anchor_id=append_anchor_id)" in source
    assert "anchor.getBoundingClientRect().top" in source
    assert '.props(f"id={browse_item_dom_id(item)}")' in source


def test_organization_browser_selectors_have_persistent_confirmation_action():
    source = inspect.getsource(index)
    assert '"Clear selection"' not in source
    assert 'f"Select {selection_mode.replace(\'_\', \' \')}"' in source
    assert "selection_confirm_button.disable()" in source
    assert "selection_confirm_button.enable()" in source
    assert "apply_relationship_selection(" in source
    assert '"dblclick", lambda _, item=node: confirm_node_selection(item)' in source
    assert '"dblclick", lambda _, action=confirm_search_result: action()' in source
    assert "await confirm_browser_selection()" in source
    assert "organization-browser-selected" in source
    assert "organization_node_dom_id(node)" in source
    assert "persist(); render_tree(); await render_summary(node)" not in source


def test_organization_browser_hides_detail_links_without_destination_privilege():
    source = inspect.getsource(index)
    assert 'can_open_organization_detail(node["type"], privileges)' in source
    assert '(auth_state.get("principal") or {}).get("global_privileges", [])' in source


def test_browsed_relationship_selection_adds_option_and_value_atomically():
    class FakeControl:
        def __init__(self):
            self.options = {1: "Existing user"}
            self.value = None

        def set_options(self, options, *, value):
            self.options = options
            self.value = value

    control = FakeControl()
    apply_relationship_selection(control, 42, "Selected user")
    assert control.options == {1: "Existing user", 42: "Selected user"}
    assert control.value == 42


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


def test_organizational_ownership_is_presented_on_details_and_dashboard():
    source = inspect.getsource(index)
    assert '"Owning organizational unit"' in source
    assert "await api.dashboard_summary(" in source
    assert 'dashboard_load_state = {"running": False}' in source
    assert 'if dashboard_load_state["running"]:' in source
    assert 'ui.label("Holdings by organizational unit")' in source
    assert "where you currently have an effective" in source
    assert "Counts include only aggregations and records you are allowed to view." in source
    assert "owner_count['aggregation_count']" in source
    assert "owner_count['record_count']" in source


def test_metadata_editor_shows_read_only_owning_org_unit_context():
    source = inspect.getsource(index)
    assert '"Owning organizational unit", value=owner_label' in source
    assert '.props("outlined readonly")' in source
    assert "Move the resource through the governed move action to change it." in source


def test_record_creation_explains_and_enforces_parent_owner_role_context():
    source = inspect.getsource(index)
    parent_position = source.index('controls["aggregation_id"] = field_input(')
    create_for_position = source.index('label="Create for *"', parent_position)
    assert parent_position < create_for_position
    assert "Select the role that will receive creator access. The record belongs to the" in source
    assert "parent aggregation's organizational unit." in source
    assert 'role="status" aria-live="polite"' in source
    assert "previous Create for selection was cleared" in source
    assert "you cannot create a record there" in source
    assert "previous_role_id in eligible_role_ids" in source


def test_aggregation_creation_places_parent_before_role_and_explains_ownership():
    source = inspect.getsource(index)
    aggregation_parent_position = source.index(
        'controls["parent_aggregation_id"] = field_input('
    )
    aggregation_create_for_position = source.index(
        'label="Create for *"', aggregation_parent_position
    )
    assert aggregation_parent_position < aggregation_create_for_position
    assert "Optional. Leave this blank to create a root aggregation" in source
    assert "select a parent" in source
    assert "For a child aggregation, the parent determines the owning organizational unit" in source
    assert "For a root" in source
    assert "aggregation, Create for determines both." in source
    assert "cannot add a child aggregation there" in source
    assert "previous Create for selection was cleared" in source


def test_required_fields_are_visually_marked_and_explained():
    source = inspect.getsource(index)
    field_source = inspect.getsource(field_input)
    assert 'f"{field.label} *" if field.required else field.label' in field_source
    assert source.count('ui.label("* Required fields")') >= 2
    assert source.count('label="Create for *"') == 2


def test_governed_move_and_root_ownership_correction_are_exposed():
    source = inspect.getsource(index)
    assert source.count('"Advanced", caption="Specialist') == 2
    assert source.count('icon="tune", value=False') == 2
    assert "show_aggregation_move" in source
    assert "show_ownership_correction_action" in source
    assert "show_acl_defaults" in source
    assert 'ui.label("Correct ownership")' in source
    assert '"Correct owner and creator ACL role"' in source
    assert 'api.correct_ownership(' in source
    assert 'api.acl_move_preview(' in source
    assert 'api.move_with_acl(' in source
    assert '"This move changes organizational ownership' in source


def test_acl_editor_presents_contextual_org_unit_members_principal():
    source = inspect.getsource(index)
    assert '"Add all org unit members"' in source
    assert '"principal_type": "org_unit_members"' in source
    assert 'ui.label("All org unit members")' in source
    assert "Membership updates automatically when role assignments change." in source
    assert "Everyone currently working in" in source


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
def test_review_and_location_experience_has_accessible_text_labels():
    source = APP_SOURCE
    assert 'ui.label("Review reminders")' in source
    assert 'ui.label("Change location")' in source
    assert 'ui.input("Assigned location"' in source
    assert 'ui.input("Current location"' in source
    assert 'ui.textarea("Reason *")' in source
    assert '"Inherited assigned location", record.get("effective_assigned_location")' in source
    assert '"Inherited current location", record.get("effective_current_location")' in source
    assert '"Record status"' not in source
    assert '"Closure state"' not in source
    assert '"View all", icon="arrow_forward"' in source
    assert '"Review", review_display(record.get("date_of_next_review"))' in source
    assert '("Vital status", "Vital" if record.get("is_vital") else "Not vital")' in source
    assert '("Vital status", "Vital" if current.get("is_vital") else "Not vital")' in source
    assert '("Medium", medium_label(record.get("medium")))' in source
    assert '("Medium", medium_label(current.get("medium")))' in source
    assert 'color="red-8" if record.get("is_vital") else "blue-grey-7"' in source
    assert 'color="red-8" if current.get("is_vital") else "blue-grey-7"' in source
    assert 'ui.label("Vital record")' in source
    assert "This record is protected from deletion while its vital status applies." in source
    assert 'ui.badge("Vital", color="red-8")' not in source
    assert '"Change this aggregation\'s assigned or current physical location"' in source
    assert '"Change whether this aggregation is protected as vital"' in source
    assert '"Change whether this record is protected as vital"' in source
    assert '"Reason for change"' in source
    assert '"Reason for changing the medium"' not in source
    assert '"Reason for lowering the security level"' not in source
