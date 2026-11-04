import pytest

from frontend.webui.session_client import session_client_summary


@pytest.mark.parametrize('agent, expected', [
    ('WathiqMobile/0.1 (ios)', ('Wathiq Mobile', 'iOS')),
    ('WathiqMobile/0.1 (android)', ('Wathiq Mobile', 'Android')),
    ('WathiqMobile/12.3.4 (ios)', ('Wathiq Mobile', 'iOS')),
    ('Mozilla/5.0 (Linux; Android 15) Chrome/130.0', ('Google Chrome', 'Android')),
    ('Mozilla/5.0 (iPhone) Safari/604.1', ('Safari', 'iOS')),
    ('Mozilla/5.0 (Macintosh) Chrome/130.0 Edg/130.0', ('Microsoft Edge', 'macOS')),
    (None, ('Browser', 'Unknown platform')),
    ('WathiqMobile/0.1 (unknown)', ('Browser', 'Unknown platform')),
])
def test_recorded_session_client(agent, expected):
    assert session_client_summary(agent) == expected


@pytest.mark.parametrize('agent, platform', [
    ('WathiqMobile/0.1 (android; model=Google Pixel 8)', 'Google Pixel 8 (Android)'),
    ('WathiqMobile/0.1 (ios; model=iPhone17,1)', 'iPhone17,1 (iOS)'),
    ('WathiqMobile/0.1 (ios; model=iPhone17,1 Simulator)', 'iPhone17,1 Simulator (iOS)'),
])
def test_mobile_model_display(agent, platform):
    assert session_client_summary(agent) == ('Wathiq Mobile', platform)
