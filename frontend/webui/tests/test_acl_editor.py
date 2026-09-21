from frontend.webui.acl_editor import acl_grants_payload, dependents_of, permission_closure


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


def test_acl_grants_payload_removes_read_only_presentation_fields():
    principals = [
        {
            "principal_type": "everyone", "role_id": None,
            "display_name": "Everyone", "role_code": None,
            "permission_codes": ["aggregation.view"],
        },
        {
            "principal_type": "org_unit_members", "role_id": None,
            "display_name": "All org unit members", "role_code": None,
            "permission_codes": ["aggregation.view", "aggregation.history.view"],
        },
        {
            "principal_type": "role", "role_id": 7,
            "display_name": "Head (Digital Records Section)", "role_code": "DRS-HD",
            "permission_codes": ["aggregation.view"],
        },
    ]

    assert acl_grants_payload(principals) == [
        {
            "principal_type": "everyone", "role_id": None,
            "permission_codes": ["aggregation.view"],
        },
        {
            "principal_type": "org_unit_members", "role_id": None,
            "permission_codes": ["aggregation.view", "aggregation.history.view"],
        },
        {
            "principal_type": "role", "role_id": 7,
            "permission_codes": ["aggregation.view"],
        },
    ]
