"""Non-blocking local message-capture prerequisite check; no database access."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


def check() -> None:
    configured = os.environ.get("MESSAGING_PDF_VALIDATOR", "verapdf")
    executable = shutil.which(configured) if configured else None
    reason = "not found or not executable"
    if executable:
        try:
            result = subprocess.run(
                [executable, "--version"], capture_output=True, timeout=10,
                check=False,
            )
            if result.returncode == 0:
                return
            reason = "could not start (check its Java runtime)"
        except (OSError, subprocess.TimeoutExpired):
            reason = "could not start within 10 seconds (check its Java runtime)"
    print(
        f"WARNING: Message capture PDF validator is {reason}: {configured!r}.\n"
        "Message capture (Save record) requires veraPDF and Java to validate "
        "PDF/A-2u and PDF/UA-1. Other application features can still start.\n"
        "From the repository root run: bash tools/install-local-tools.sh\n"
        "That command displays installation steps; it does not download tools.\n"
        "Then set MESSAGING_PDF_VALIDATOR to the installed executable in .env.\n"
        "See docs/local-tooling.md and docs/upgrades/message-capture-validator.md.\n",
        file=sys.stderr,
    )


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parents[1])
    check()
