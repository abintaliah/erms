from frontend.webui.rtl import document_direction_script, normalize_direction


def test_direction_is_closed_to_the_supported_values():
    assert normalize_direction("rtl") == "rtl"
    assert normalize_direction("RTL") == "rtl"
    assert normalize_direction("sideways") == "ltr"


def test_direction_script_updates_root_portals_and_future_dynamic_content():
    script = document_direction_script("ar", "rtl")
    assert "document.documentElement.lang = language" in script
    assert "document.documentElement.dir = direction" in script
    assert "MutationObserver" in script
    assert ".q-menu, .q-dialog, .q-notifications" in script
    assert "localStorage.setItem('wathiq.direction', direction)" in script
    assert 'const language = "ar"' in script
