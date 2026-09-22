from pathlib import Path


APP = Path(__file__).parents[1] / "app.py"
CLIENT = Path(__file__).parents[1] / "api_client.py"


def test_holds_workspace_and_navigation_are_wired():
    source = APP.read_text(encoding="utf-8")
    assert '"Holds", "gavel", navigation_key="holds"' in source
    assert 'async def select_holds()' in source
    assert 'async def select_hold_details(hold_id: int)' in source
    assert 'async def open_hold_editor(' in source
    assert '"Create hold"' in source
    assert '"Add Members"' in source
    assert '"Search number, title or description"' in source
    assert 'first_page=ui.button("First"' in source
    assert 'last_page=ui.button("Last"' in source
    assert '<q-tooltip>Open resource</q-tooltip>' in source
    assert '<q-tooltip>Remove from this hold</q-tooltip>' in source
    assert '"Remove from all holds"' in source
    assert 'color="positive" if hold["state"]=="active" else "blue-grey"' in source
    assert 'render_user_avatar(contributor, size="28px").style(' in source
    assert '"margin-right:8px !important"' in source
    assert 'member_assigned_from=ui.input("Assignment date from")' in source
    assert 'member_assigned_before=ui.input("Assignment date before")' in source
    assert '"width:1280px;max-width:calc(100vw - 48px)"' in source
    assert '"width: 260px; min-width: 260px; text-align: left"' in source
    assert 'candidate_table.add_slot("body-cell-resource_type"' in source
    assert '"width: 88px; max-width: 88px; text-align: left; white-space: nowrap"' in source
    assert source.count('style="width:88px;max-width:88px;text-align:left"') == 1
    assert 'style="width:38px;max-width:38px;text-align:left"' in source
    assert '"width: 240px; min-width: 240px; text-align: left"' in source
    assert '"width: 90px; white-space: normal; text-align: left"' in source
    assert '.hold-selection-table .q-table th:first-child' in source
    assert '"w-full governance-table hold-selection-table"' in source
    assert '.hold-candidate-selection-table .q-table th:first-child' in source
    assert '"w-full governance-table hold-selection-table hold-candidate-selection-table"' in source
    assert 'candidate_table.add_slot("body-cell-title"' in source
    assert 'candidate_table.add_slot("body-cell-description"' in source
    assert 'on_click=lambda: select_user_details(hold["owner"]["id"])' in source
    assert 'props.row.resource_type === \'aggregation\' ? \'folder\' : \'description\'' in source
    assert 'height:88px;overflow-y:auto;white-space:normal' in source
    assert '"body-cell-title"' in source
    assert ').props("flat dense no-caps color=blue-grey-9").classes("gap-2")' in source
    assert 'row["assigned_at_display"] = format_timestamp(row["assigned_at"])' in source
    assert 'props.row.security_level_code' not in source  # composed once in Python
    assert 'row["security_level_display"] = f"{row[\'security_level_code\']} — {row[\'security_level_name\']}"' in source
    assert 'table.on("open_user", lambda event: select_user_details(int(event.args)))' in source


def test_hold_mutations_collect_reasons_and_refresh_live_state():
    source = APP.read_text(encoding="utf-8")
    assert 'async def hold_reason_dialog(' in source
    assert 'Reason for updating this hold' in source
    assert 'Reason for removing this direct assignment' in source
    assert 'Remove from all holds? Inherited protection from parent aggregations will remain.' in source
    assert 'Remove from all holds? Inherited protection from its aggregation hierarchy will remain.' in source
    assert 'await api.effective_holds("record", record_id)' in source
    assert 'await api.effective_holds("aggregation", current["id"])' in source
    assert 'effective_holds, "record", record_id' in source
    assert 'effective_holds, "aggregation", current["id"]' in source
    assert 'Remove from this hold' in source


def test_access_explainer_renders_redaction_safe_hold_constraints():
    source = APP.read_text(encoding="utf-8")
    assert 'result.get("resource_state_constraints", [])' in source
    assert 'details restricted' in source
    assert 'An effective legal hold prevents this' in source


def test_security_level_change_remains_separate_from_hold_frozen_metadata():
    source = APP.read_text(encoding="utf-8")
    assert 'async def show_security_level_change(' in source
    assert 'if capabilities.get("change_security_level"):' in source
    assert 'await api.preview_security_level_change({' in source
    assert 'await api.apply_security_level_change({' in source
    assert '"Reason *"' in source
    assert '"security_level_id",' in source
    assert '"Level action for a reviewed security-level change."' in source
    assert '"none": "Change only this resource"' in source
    assert '"raise_ancestors": "Also raise parent aggregations as needed"' in source
    assert '"downgrade_subtree": "Also lower contained resources as needed"' in source
    assert "props.opt.value === 0" in source
    assert 'popup-content-style="width:572px;max-width:calc(100vw - 64px)"' in source
    assert "white-space:normal; overflow-wrap:anywhere" in source


def test_api_client_exposes_complete_hold_workflow():
    source = CLIENT.read_text(encoding="utf-8")
    for method in (
        "holds", "hold", "create_hold", "update_hold", "delete_hold",
        "hold_members", "hold_contributors", "replace_hold_contributors",
        "add_hold_member", "hold_member_candidates", "add_hold_members_bulk",
        "remove_hold_member", "effective_holds",
        "add_resource_to_hold", "remove_resource_from_hold",
        "remove_all_direct_holds", "hold_history",
    ):
        assert f"async def {method}(" in source
