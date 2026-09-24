from pathlib import Path

from backend.services.api.xml_to_html import build_xml_html, decode_xml_source


def test_bilingual_xml_is_rendered_as_escaped_source():
    fixture = (
        Path(__file__).parents[4]
        / "examples/samples/docs/xml/sample-1108-asset-management-mixed.xml"
    )

    rendered = build_xml_html(fixture)

    assert '<meta charset="utf-8">' in rendered
    assert "&lt;wathiq-sample" in rendered
    assert "Asset Register Review" in rendered
    assert "مراجعة سجل الأصول" in rendered
    assert "<wathiq-sample" not in rendered


def test_xml_declared_utf16_encoding_is_honoured():
    source = '<?xml version="1.0" encoding="utf-16"?><title>مراجعة</title>'

    assert decode_xml_source(source.encode("utf-16")) == source
