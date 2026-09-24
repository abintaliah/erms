#!/usr/bin/env python3
"""Render corpus pages, check image bounds, and produce QA contact sheets."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageOps
from pypdf import PdfReader


def render_pdfs(source: Path, target: Path, pdftoppm: str) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    outputs = []
    for pdf in sorted(source.glob("*.pdf")):
        output = target / pdf.stem
        result = subprocess.run(
            [pdftoppm, "-f", "1", "-singlefile", "-r", "80", "-png", str(pdf), str(output)],
            capture_output=True, text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr)
        outputs.append(output.with_suffix(".png"))
    return outputs


def content_bbox(image: Image.Image):
    rgb = image.convert("RGB")
    background = Image.new("RGB", rgb.size, "white")
    return ImageChops.difference(rgb, background).getbbox()


def contact_sheets(images: list[Path], output: Path, label: str) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    sheets = []
    thumb_size = (250, 354)
    per_sheet = 16
    for batch, start in enumerate(range(0, len(images), per_sheet), 1):
        canvas = Image.new("RGB", (1080, 1530), "#D9E2EC")
        draw = ImageDraw.Draw(canvas)
        draw.text((20, 10), f"{label} contact sheet {batch}", fill="black")
        for offset, image_path in enumerate(images[start:start + per_sheet]):
            image = Image.open(image_path).convert("RGB")
            image.thumbnail(thumb_size)
            col, row = offset % 4, offset // 4
            x, y = 20 + col * 265, 45 + row * 365
            framed = ImageOps.expand(image, border=1, fill="#66788A")
            canvas.paste(framed, (x, y))
            draw.text((x, y + 356), image_path.stem[:34], fill="black")
        path = output / f"{label}-{batch:02d}.jpg"
        canvas.save(path, quality=88)
        sheets.append(path)
    return sheets


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    pdftoppm = sys.argv[2]
    qa = root / ".qa"
    qa.mkdir(exist_ok=True)
    docx_images = render_pdfs(root / ".qa-rendered-pdf", qa / "docx", pdftoppm)
    pdf_images = render_pdfs(root / "pdf", qa / "pdf", pdftoppm)
    groups = {
        "docx": docx_images,
        "xlsx": sorted((root / ".qa-xlsx-png").glob("*.png")),
        "pdf": pdf_images,
        "png": sorted((root / "png").glob("*.png")),
        "jpeg": sorted((root / "jpeg").glob("*.jpeg")),
        "pptx": sorted((root / ".qa-pptx").glob("*.png")),
    }
    errors = []
    stats = {}
    for label, images in groups.items():
        expected_count = 160 if label == "pptx" else 143
        if len(images) != expected_count:
            errors.append(f"{label}: expected {expected_count} images, found {len(images)}")
        dimensions = set()
        for path in images:
            image = Image.open(path)
            dimensions.add(image.size)
            bbox = content_bbox(image)
            if bbox is None:
                errors.append(f"blank image: {path}")
                continue
            left, top, right, bottom = bbox
            width, height = image.size
            if label not in {"xlsx", "pptx"} and (left <= 1 or top <= 1 or right >= width - 1 or bottom >= height - 1):
                errors.append(f"content touches edge: {path} bbox={bbox} size={image.size}")
        sheets = contact_sheets(images, qa / "contact-sheets", label)
        stats[label] = {"count": len(images), "dimensions": sorted(map(list, dimensions)), "contact_sheets": len(sheets)}
    for pdf in sorted((root / "pdf").glob("*.pdf")):
        if len(PdfReader(pdf).pages) != 1:
            errors.append(f"PDF is not one page: {pdf}")
    report = {"groups": stats, "errors": errors}
    (root / "visual-validation-summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit("\n".join(errors[:30]))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
