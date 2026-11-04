"""Privacy-minimizing presentation of recorded session user agents."""

import re


_MOBILE_AGENT = re.compile(r"WathiqMobile/[0-9]+(?:\.[0-9]+)* \((ios|android)(?:; model=([A-Za-z0-9 ,._+/-]{1,100}))?\)")


def session_client_summary(user_agent: str | None) -> tuple[str, str]:
    """Return client/product and platform without changing audit evidence."""
    value = user_agent or ""
    mobile = _MOBILE_AGENT.fullmatch(value)
    if mobile:
        platform = {"ios": "iOS", "android": "Android"}[mobile[1]]
        if mobile[2]:
            platform = f"{mobile[2]} ({platform})"
        return "Wathiq Mobile", platform
    browser = next((name for token, name in (
        ("Edg/", "Microsoft Edge"), ("Chrome/", "Google Chrome"),
        ("Firefox/", "Mozilla Firefox"), ("Safari/", "Safari"),
    ) if token in value), "Browser")
    platform = next((name for token, name in (
        ("Macintosh", "macOS"), ("Windows", "Windows"), ("Android", "Android"),
        ("iPhone", "iOS"), ("Linux", "Linux"),
    ) if token in value), "Unknown platform")
    return browser, platform
