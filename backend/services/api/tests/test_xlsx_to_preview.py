from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET

from backend.services.api.xlsx_to_preview import prepare_xlsx_for_preview


SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def test_wide_xlsx_is_normalized_to_one_landscape_page_wide(tmp_path):
    fixture = (
        Path(__file__).parents[4]
        / "examples/samples/docs/xlsx/sample-0283-general-administration-mixed.xlsx"
    )
    prepared = tmp_path / "prepared.xlsx"
    original = fixture.read_bytes()

    assert prepare_xlsx_for_preview(fixture, prepared)
    assert fixture.read_bytes() == original

    with zipfile.ZipFile(prepared) as archive:
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        names = set(archive.namelist())
    namespace = {"x": SPREADSHEET_NS}
    page_setup = root.find("./x:pageSetup", namespace)
    setup_properties = root.find("./x:sheetPr/x:pageSetUpPr", namespace)

    assert page_setup is not None
    assert page_setup.get("fitToWidth") == "1"
    assert page_setup.get("fitToHeight") == "0"
    assert page_setup.get("orientation") == "landscape"
    assert setup_properties is not None
    assert setup_properties.get("fitToPage") == "1"
    assert "xl/styles.xml" in names
