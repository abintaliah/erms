# Local tooling setup

This repository intentionally keeps machine-specific tools and editor state out of Git.

## PDF validation

Message capture (**Save record** for a message) requires the independent
veraPDF CLI and its Java runtime. Other application features do not require
veraPDF. Both PDF/A-2u and PDF/UA-1 validation must succeed before capture can
commit. Missing tooling does not disable ordinary messaging or prevent startup.

Each colleague must install these tools locally after cloning or syncing a fork:
`.local-tools/` is deliberately ignored by Git. Python requirements and database
migrations do not install the validator. Wathiq capture acceptance verification
used veraPDF 1.30.2; see [deployment requirements](deployment.md).

From the repository root, run:

```bash
bash tools/install-local-tools.sh
```

This helper prints manual installation instructions and exits with status 1
until the expected executable exists. It does not download or install software.

1. Install a Java runtime supported by your veraPDF package. The macOS Java 17
   setup is in [local setup](full-text-search-local-setup.md).
2. Download a stable Greenfield installer from the
   [official veraPDF installation guide](https://docs.verapdf.org/install/).
3. Extract the installer archive, run its `vera-install` launcher on macOS/Linux
   (`vera-install.bat` on Windows), and choose the repository's
   `.local-tools/verapdf` as the installation directory. Include the CLI/startup
   scripts. Extracting an installer archive alone does not install the CLI.
4. Confirm the executable and Java runtime work:

   ```bash
   java -version
   ./.local-tools/verapdf/verapdf --version
   ```

5. Set this in the root `.env` (or use an absolute executable path):

   ```dotenv
   MESSAGING_PDF_VALIDATOR=.local-tools/verapdf/verapdf
   ```

If your package installs its launcher at a different location, use that exact
path. An explicitly configured path takes precedence; there is no silent
fallback to another installation. If the variable is absent, capture uses
`verapdf` on PATH.

`run-local-stack.sh` checks the resolved environment after loading `.env`, even
when it reuses an existing API. A missing/non-executable validator or failing
`--version` check prints a warning, the helper command and the affected feature.
The probe has a ten-second timeout and continues startup; it does not validate
a PDF or replace the independent checks performed for every capture. Restart
an existing API after changing its environment.

For a standalone check, export the same setting and run:

```bash
MESSAGING_PDF_VALIDATOR=.local-tools/verapdf/verapdf python3 tools/check_local_pdf_validator.py
```

The standalone checker does not load `.env`; it uses its process environment.
See the [upgrade note](upgrades/message-capture-validator.md).

## Local editor state

The repo also ignores `.kile.jsonc` and any local editor state files so they do not get committed.

The Git ignore rules already cover:

- `.local-tools/`
- `.kile.jsonc`
- `kile.jsonc`

These settings are meant to remain local to each machine, not to be shared in the source repository.

### macOS renderer library path

If WeasyPrint reports that it cannot load GObject/Pango despite Homebrew
libraries being installed, configure the installed library directory in `.env`:

```dotenv
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
```

Use the actual Homebrew library directory on your machine and restart the API.
This follows the official WeasyPrint missing-library troubleshooting guidance:
https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#missing-library
