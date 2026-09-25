from __future__ import annotations

import os
import hashlib
import resource
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class ExtractionError(RuntimeError):
    def __init__(self, code: str, summary: str, retryable: bool = False):
        super().__init__(summary)
        self.code, self.summary, self.retryable = code, summary[:500], retryable


APP_JAR_SHA512 = "5ad62881281d70e7db029c97f1efb3ac351343f27dfe2361e6351b84bcd7878675c368b2946adc6ea6ba630f6e1b211f43a59a81a9a0a26a5d8b279aced341dc"


def app_jar(home: Path) -> Path:
    jars = list(home.glob("tika-app-4.0.0.jar"))
    if len(jars) != 1 or not (home / "lib").is_dir():
        raise RuntimeError("TEXT_INDEXER_TIKA_HOME must be the complete official Tika 4.0.0 app distribution")
    return jars[0]


def self_test(home: Path) -> None:
    jar = app_jar(home)
    digest=hashlib.sha512()
    with jar.open("rb") as stream:
        while block:=stream.read(1024*1024): digest.update(block)
    if digest.hexdigest()!=APP_JAR_SHA512:
        raise RuntimeError("Tika app jar checksum does not match the pinned official distribution")
    if shutil.which("java") is None:
        raise RuntimeError("Java 17 or newer is required")
    version = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=10)
    if version.returncode:
        raise RuntimeError("Java is not runnable")
    listing = subprocess.run(["jar", "tf", str(jar)], capture_output=True, text=True, timeout=20)
    combined = listing.stdout
    for library in (home / "lib").glob("*.jar"):
        if "tika-pipes-fork-parser" in library.name:
            combined += library.name
    if "tika-pipes-fork-parser" not in combined and "PipesForkParser" not in combined:
        raise RuntimeError("official distribution lacks tika-pipes-fork-parser")
    for command in ("tesseract","pdfinfo","pdftoppm"):
        if shutil.which(command) is None:
            raise RuntimeError(f"{command} is required")


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (120, 125))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
    if sys.platform.startswith("linux") and hasattr(resource, "RLIMIT_NPROC"):
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))


def extract(home: Path, source: Path, timeout: int) -> str:
    jar = app_jar(home)
    config = Path(__file__).with_name("tika-config.json")
    milliseconds = timeout * 1000
    command = [
        "java", "-Xmx768m", "-jar", str(jar), f"--config={config}", "--fork",
        f"--task-timeout={milliseconds}", f"--progress-timeout={min(milliseconds, 60_000)}",
        "--fork-jvm-args=-Xmx768m", "--maxEmbeddedDepth=0", "--text", str(source),
    ]
    # The Tika Pipes fork isolates parser work. Deployment-level egress denial is
    # additionally mandatory; this worker itself never supplies network inputs.
    try:
        result = subprocess.run(
            command, cwd=home, capture_output=True, text=True, timeout=timeout,
            preexec_fn=_limits if os.name == "posix" else None,
            env={"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8", "TMPDIR": str(source.parent)},
        )
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError("timeout", "extractor exceeded wall-clock limit", True) from exc
    if result.returncode:
        detail = (result.stderr or "extractor rejected content").casefold()
        code = "password_protected" if "password" in detail else "corrupt"
        raise ExtractionError(code, "extractor rejected content")
    return result.stdout


def extract_image_ocr(source: Path, timeout: int) -> str:
    if shutil.which("tesseract") is None:
        raise ExtractionError("extractor_unavailable", "Tesseract is not runnable", True)
    try:
        result = subprocess.run(
            ["tesseract", str(source), "stdout", "-l", "eng+ara", "--psm", "6"],
            capture_output=True,text=True,timeout=timeout,
            preexec_fn=_limits if os.name=="posix" else None,
            env={"PATH":os.environ.get("PATH",""),"LANG":"C.UTF-8","TMPDIR":str(source.parent)},
        )
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError("timeout","OCR exceeded wall-clock limit",True) from exc
    if result.returncode:
        raise ExtractionError("corrupt","OCR rejected image content")
    return result.stdout


def pdf_page_count(source: Path, timeout: int = 20) -> int:
    try:
        result=subprocess.run(
            ["pdfinfo",str(source)],capture_output=True,text=True,timeout=timeout,
            preexec_fn=_limits if os.name=="posix" else None,
            env={"PATH":os.environ.get("PATH",""),"LANG":"C.UTF-8","TMPDIR":str(source.parent)},
        )
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError("timeout","PDF inspection exceeded wall-clock limit",True) from exc
    if result.returncode:
        raise ExtractionError("corrupt","PDF metadata inspection failed")
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":",1)[1].strip())
    raise ExtractionError("corrupt","PDF page count is unavailable")


def extract_pdf(home: Path,source: Path,timeout: int,max_pages: int,max_temp_bytes: int) -> tuple[str,bool]:
    pages=pdf_page_count(source,min(timeout,20))
    if pages>max_pages:
        raise ExtractionError("limit_exceeded","PDF exceeds configured page limit")
    native=extract(home,source,timeout)
    with tempfile.TemporaryDirectory(prefix="pdf-ocr-",dir=source.parent) as directory:
        prefix=Path(directory)/"page"
        try:
            rendered=subprocess.run(
                ["pdftoppm","-png","-r","200","-f","1","-l",str(pages),str(source),str(prefix)],
                capture_output=True,text=True,timeout=timeout,
                preexec_fn=_limits if os.name=="posix" else None,
                env={"PATH":os.environ.get("PATH",""),"LANG":"C.UTF-8","TMPDIR":directory},
            )
        except subprocess.TimeoutExpired as exc:
            raise ExtractionError("timeout","PDF OCR rendering exceeded wall-clock limit",True) from exc
        if rendered.returncode:
            raise ExtractionError("corrupt","PDF OCR rendering failed")
        images=sorted(Path(directory).glob("page-*.png"))
        if len(images)!=pages or sum(image.stat().st_size for image in images)>max_temp_bytes:
            raise ExtractionError("limit_exceeded","PDF OCR temporary output exceeds configured limit")
        ocr="\n\n".join(extract_image_ocr(image,timeout) for image in images)
    native_arabic=sum('\u0600'<=character<='\u06ff' for character in native)
    ocr_arabic=sum('\u0600'<=character<='\u06ff' for character in ocr)
    # The Tika 4.0.0 fork currently loses its configured Arabic OCR language.
    # Prefer explicit bilingual OCR only when it recovers materially more Arabic;
    # otherwise retain the higher-fidelity native text extraction.
    return (ocr,True) if ocr_arabic>max(20,native_arabic*2) else (native,False)
