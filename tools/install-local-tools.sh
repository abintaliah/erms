#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_TOOLS_DIR="$REPO_ROOT/.local-tools"
VERAPDF_DIR="$LOCAL_TOOLS_DIR/verapdf"
VERAPDF_BIN="$VERAPDF_DIR/verapdf"

mkdir -p "$LOCAL_TOOLS_DIR"

if [ -x "$VERAPDF_BIN" ]; then
  echo "veraPDF CLI already installed at $VERAPDF_BIN"
  exit 0
fi

cat <<'EOF'
veraPDF is intentionally kept out of Git because it is local developer tooling.

To install it for this repository:

1. Install Java supported by your veraPDF package (local setup documents Java 17).
2. Download a stable Greenfield installer from the official guide:
   https://docs.verapdf.org/install/
3. Extract the installer, run vera-install (macOS/Linux) or vera-install.bat
   (Windows), and choose this repository's .local-tools/verapdf as the target.
   Include the CLI/startup scripts; extracting the archive alone is not enough.
4. Verify the installation:
      java -version
      ./.local-tools/verapdf/verapdf --version
5. Copy .env.example to .env if needed, and set:
      MESSAGING_PDF_VALIDATOR=.local-tools/verapdf/verapdf
   Use the exact executable path if your package installs it elsewhere.

This helper displays steps only; it does not download or install software.
See docs/local-tooling.md for details and the standalone availability check.

The repo ignores .local-tools and .kile.jsonc so local-only settings stay out of Git.
EOF

exit 1
