from frontend.webui.acl_editor import dependents_of, permission_closure


def test_permission_closure_adds_transitive_record_prerequisites():
    assert permission_closure({"record.component.share"}) == {
        "record.component.share", "record.component.view",
        "record.component.list", "record.view",
    }


def test_permission_closure_adds_aggregation_view():
    assert permission_closure({"aggregation.delete"}) == {
        "aggregation.delete", "aggregation.view",
    }


def test_dependents_identifies_permissions_removed_with_prerequisite():
    selected = {"record.view", "record.component.list", "record.component.download"}
    assert dependents_of("record.view", selected) == {
        "record.component.list", "record.component.download",
    }
