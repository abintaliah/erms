from frontend.webui.capabilities import (
    NAVIGATION_PRIVILEGES, can_navigate, can_open_organization_detail, capability_allowed,
    dashboard_administration_resources,
)


def test_unprivileged_principal_cannot_see_administration_destinations():
    for key in (
        "classification-schemes", "org-units", "roles", "users",
        "audit-trail", "login-sessions", "security-levels", "profiles",
        "governance-custody",
        "security-operations",
        "aggregations", "records",
    ):
        assert not can_navigate(key, ())
    assert can_navigate("dashboard", ())
    assert not can_navigate("organization-browser", ())
    assert can_navigate("organization-browser", {"organization.browse"})


def test_information_resource_destinations_require_their_exact_view_privilege():
    assert can_navigate("aggregations", {"aggregation.view"})
    assert not can_navigate("records", {"aggregation.view"})
    assert can_navigate("records", {"record.view"})
    assert not can_navigate("aggregations", {"record.view"})
    assert not can_navigate("organization-browser", ())
    assert can_navigate("organization-browser", {"organization.browse"})


def test_navigation_and_dashboard_are_derived_from_exact_privileges():
    privileges = {"organization.administer", "audit.view"}
    assert can_navigate("roles", privileges)
    assert can_navigate("org-units", privileges)
    assert can_navigate("audit-trail", privileges)
    assert not can_navigate("users", privileges)
    assert not can_navigate("profiles", privileges)
    assert dashboard_administration_resources(privileges) == ("org-units", "roles")


def test_organization_browser_only_offers_detail_pages_the_principal_can_open():
    assert not can_open_organization_detail("org_unit", ())
    assert not can_open_organization_detail("role", ())
    assert not can_open_organization_detail("user", ())
    assert can_open_organization_detail("org_unit", {"organization.administer"})
    assert can_open_organization_detail("role", {"organization.administer"})
    assert not can_open_organization_detail("user", {"organization.administer"})
    assert can_open_organization_detail("user", {"identity.users.administer"})
    assert not can_open_organization_detail("role", {"identity.users.administer"})
    assert not can_open_organization_detail("unknown", {"organization.administer"})


def test_catalogues_are_not_standalone_navigation_destinations():
    assert "privileges" not in NAVIGATION_PRIVILEGES
    assert "permissions" not in NAVIGATION_PRIVILEGES


def test_governed_capabilities_fail_closed_when_a_response_field_is_missing():
    assert capability_allowed(None, "remove_component")
    assert capability_allowed({"remove_component": True}, "remove_component")
    assert not capability_allowed({}, "remove_component")
    assert not capability_allowed({"remove_component": False}, "remove_component")
