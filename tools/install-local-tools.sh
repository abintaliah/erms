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

1. Visit the official veraPDF releases page:
   https://github.com/veraPDF/veraPDF-validation/releases
2. Download the latest stable CLI archive for your platform.
3. Extract it into this repo's .local-tools directory:
      mkdir -p .local-tools
      unzip /path/to/verapdf-archive.zip -d .local-tools/
   or unpack the tarball into the same folder.
4. Ensure the CLI is available at:
      ./.local-tools/verapdf/verapdf
5. Copy .env.example to .env if needed, and set:
      MESSAGING_PDF_VALIDATOR=.local-tools/verapdf/verapdf

The repo ignores .local-tools and .kile.jsonc so local-only settings stay out of Git.
EOF

exit 1
