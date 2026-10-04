# Local tooling setup

This repository intentionally keeps machine-specific tools and editor state out of Git.

## PDF validation

The messaging subsystem uses the local veraPDF CLI. The binary is expected at:

```
.local-tools/verapdf/verapdf
```

Install it with the official veraPDF release package and place it under the repository's `.local-tools` directory.

1. Open the veraPDF releases page: https://github.com/veraPDF/veraPDF-validation/releases
2. Download the latest stable CLI package for your OS.
3. Extract it into the repo root under `.local-tools/`.
4. Confirm the binary exists at `.local-tools/verapdf/verapdf`.
5. In `.env`, set:

```
MESSAGING_PDF_VALIDATOR=.local-tools/verapdf/verapdf
```

## Local editor state

The repo also ignores `.kile.jsonc` and any local editor state files so they do not get committed.

The Git ignore rules already cover:

- `.local-tools/`
- `.kile.jsonc`
- `kile.jsonc`

These settings are meant to remain local to each machine, not to be shared in the source repository.
