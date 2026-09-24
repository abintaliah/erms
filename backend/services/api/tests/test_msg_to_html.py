from pathlib import Path

from backend.services.api.email_to_html import build_eml_html, build_msg_html


def test_bilingual_msg_is_extracted_to_utf8_inert_html():
    fixture = (
        Path(__file__).parents[4]
        / "examples/samples/docs/msg/sample-1041-finance-arabic.msg"
    )

    rendered = build_msg_html(fixture)

    assert '<meta charset="utf-8">' in rendered
    assert "Quarterly Finance Review WTHQ-1041" in rendered
    assert "وتتضمن المذكرة المصطلح النادر الاستعصاء" in rendered
    assert 'class="body" dir="auto"' in rendered


def test_base64_eml_is_decoded_to_utf8_inert_html():
    fixture = (
        Path(__file__).parents[4]
        / "examples/samples/docs/eml/sample-1001-finance-english.eml"
    )

    rendered = build_eml_html(fixture)

    assert '<meta charset="utf-8">' in rendered
    assert "Quarterly Finance Review WTHQ-1001" in rendered
    assert "Reference wathiqrare1001 uses the uncommon term quincunx" in rendered
    assert "وتتضمن المذكرة المصطلح النادر الاستعصاء" in rendered
    assert "UmVmZXJlbmNl" not in rendered
