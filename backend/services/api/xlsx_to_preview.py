from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_CELL_REFERENCE = re.compile(r"^([A-Z]+)")


def _column_number(reference: str) -> int:
    match = _CELL_REFERENCE.match(reference.upper())
    if not match:
        return 0
    number = 0
    for character in match.group(1):
        number = number * 26 + ord(character) - ord("A") + 1
    return number


def _used_width(root: ET.Element) -> float:
    namespace = {"x": _SPREADSHEET_NS}
    cells = root.findall(".//x:sheetData/x:row/x:c", namespace)
    maximum_column = max(
        (_column_number(cell.get("r", "")) for cell in cells),
        default=0,
    )
    widths = {column: 8.43 for column in range(1, maximum_column + 1)}
    for definition in root.findall("./x:cols/x:col", namespace):
        start = int(definition.get("min", "1"))
        end = int(definition.get("max", str(start)))
        width = 0.0 if definition.get("hidden") == "1" else float(
            definition.get("width", "8.43")
        )
        for column in range(start, min(end, maximum_column) + 1):
            widths[column] = width
    return sum(widths.values())


def _normalize_sheet(xml: bytes) -> tuple[bytes, bool]:
    ET.register_namespace("", _SPREADSHEET_NS)
    root = ET.fromstring(xml)
    namespace = {"x": _SPREADSHEET_NS}
    page_setup = root.find("./x:pageSetup", namespace)
    setup_properties = root.find("./x:sheetPr/x:pageSetUpPr", namespace)
    if (
        page_setup is not None
        and page_setup.get("fitToWidth") == "1"
        and setup_properties is not None
        and setup_properties.get("fitToPage", "").lower() in {"1", "true"}
    ):
        return xml, False
    orientation = page_setup.get("orientation", "portrait") if page_setup is not None else "portrait"
    available_width = 120 if orientation == "landscape" else 80
    if _used_width(root) <= available_width:
        return xml, False

    sheet_properties = root.find("./x:sheetPr", namespace)
    if sheet_properties is None:
        sheet_properties = ET.Element(f"{{{_SPREADSHEET_NS}}}sheetPr")
        root.insert(0, sheet_properties)
    setup_properties = sheet_properties.find("./x:pageSetUpPr", namespace)
    if setup_properties is None:
        setup_properties = ET.SubElement(
            sheet_properties,
            f"{{{_SPREADSHEET_NS}}}pageSetUpPr",
        )
    setup_properties.set("fitToPage", "1")
    setup_properties.set("autoPageBreaks", "0")

    if page_setup is None:
        page_setup = ET.Element(f"{{{_SPREADSHEET_NS}}}pageSetup")
        margins = root.find("./x:pageMargins", namespace)
        insertion = list(root).index(margins) + 1 if margins is not None else len(root)
        root.insert(insertion, page_setup)
    page_setup.attrib.pop("scale", None)
    page_setup.set("fitToWidth", "1")
    page_setup.set("fitToHeight", "0")
    page_setup.set("orientation", "landscape")
    page_setup.set("paperSize", "9")  # ISO A4
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), True


def prepare_xlsx_for_preview(source: Path, destination: Path) -> bool:
    """Copy an XLSX and normalize only worksheets wider than a printable page."""
    changed = False
    with zipfile.ZipFile(source, "r") as input_archive, zipfile.ZipFile(
        destination, "w",
    ) as output_archive:
        for item in input_archive.infolist():
            payload = input_archive.read(item.filename)
            if item.filename.startswith("xl/worksheets/sheet") and item.filename.endswith(".xml"):
                payload, normalized = _normalize_sheet(payload)
                changed = changed or normalized
            output_archive.writestr(item, payload)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare an XLSX copy for bounded PDF preview")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    changed = prepare_xlsx_for_preview(args.source, args.destination)
    print("normalized" if changed else "unchanged")


if __name__ == "__main__":
    main()
