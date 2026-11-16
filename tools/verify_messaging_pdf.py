"""Independent PDF conformance, font, Unicode and determinism evidence."""

from pathlib import Path
import re
import subprocess
from backend.services.api.messaging.capture_pdf import render, validate


def main():
    output = Path("docs/verification/messaging-phase-5")
    output.mkdir(parents=True, exist_ok=True)
    for language, direction, title, content, expected in [
        (
            "en",
            "ltr",
            "Captured message",
            '<p><strong>Sender:</strong> Example sender</p><h2>Message</h2><p>Preserve the complete conversation.</p><ul><li><p>First item</p><ol><li>Nested item</li></ol></li><li>Second item</li></ul><p><a href="https://example.org/reference">Public reference description</a></p>',
            "Preserve the complete conversation.",
        ),
        (
            "ar",
            "rtl",
            "رسالة محفوظة",
            '<p><strong>المرسل:</strong> مرسل تجريبي</p><h2>الرسالة</h2><p>مرحباً بكم في واثق. تحفظ المحادثة كاملة.</p><ul><li><p>العنصر الأول</p><ol><li>عنصر متداخل</li></ol></li><li>العنصر الثاني</li></ul><p><a href="https://example.org/reference">وصف المرجع العام</a></p>',
            "مرحباً بكم في واثق.",
        ),
    ]:
        pdf = render(title, content, language, direction)
        assert pdf == render(
            title, content, language, direction
        ), "Rendering must be deterministic"
        path = output / f"capture-{language}.pdf"
        path.write_bytes(pdf)
        fonts = subprocess.check_output(["pdffonts", str(path)], text=True)
        assert "Changa" in fonts
        for line in fonts.splitlines()[2:]:
            assert re.search(r"yes\s+yes\s+yes", line), line
        text = subprocess.check_output(["pdftotext", str(path), "-"], text=True)
        text = re.sub("[\u202a-\u202e\u2066-\u2069]", "", text)
        assert re.sub(r"\s+", "", expected) in re.sub(r"\s+", "", text), text
        subprocess.run(
            [
                "pdftoppm",
                "-scale-to",
                "1200",
                "-png",
                "-singlefile",
                str(path),
                str(path.with_suffix("")),
            ],
            check=True,
        )
        path.with_suffix(".fonts.txt").write_text(fonts)
        info = subprocess.check_output(["pdfinfo", str(path)], text=True)
        assert re.search(r"Tagged:\s+yes", info)
        links = subprocess.check_output(["pdfinfo", "-url", str(path)], text=True)
        assert "https://example.org/reference" in links
        path.with_suffix(".links.txt").write_text(links)
        for profile in ("2u", "ua1"):
            import os

            report = subprocess.run(
                [
                    os.environ.get("MESSAGING_PDF_VALIDATOR", "verapdf"),
                    "--format",
                    "xml",
                    "-f",
                    profile,
                    str(path),
                ],
                capture_output=True,
                check=True,
            )
            path.with_suffix("." + profile + ".xml").write_bytes(report.stdout)
        print(
            language
            + ": deterministic bytes, embedded Changa, Unicode, PDF/A-2u and PDF/UA-1 passed"
        )


if __name__ == "__main__":
    main()
