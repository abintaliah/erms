#!/usr/bin/env python3
"""Validate rendered PPTX fixtures and create temporary contact sheets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

from visual_qa import contact_sheets, content_bbox


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    images = sorted((root / ".qa-pptx").glob("*.png"))
    errors = []
    dimensions = set()
    if len(images) != 160:
        errors.append(f"expected 160 rendered slides, found {len(images)}")
    for path in images:
        image = Image.open(path)
        dimensions.add(image.size)
        if content_bbox(image) is None:
            errors.append(f"blank slide: {path}")
    sheets = contact_sheets(images, root / ".qa-pptx-contact-sheets", "pptx")
    report = {
        "presentations": 40, "slides": len(images),
        "dimensions": sorted(map(list, dimensions)),
        "contact_sheets": len(sheets), "errors": errors,
    }
    (root / "pptx-visual-validation-summary.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    if errors:
        raise SystemExit("\n".join(errors))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
