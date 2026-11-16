# Upgrade note: message capture PDF validator

4 October 2026

After syncing a fork with message capture support, install veraPDF and its
supported Java runtime on each machine that runs the API and needs message
**Save record**. The binary under `.local-tools/` is intentionally not committed,
so pulling code, installing Python requirements or applying migrations cannot
supply it. No database migration is needed for this tooling change.

From the repository root run `bash tools/install-local-tools.sh` to display the
manual installation steps. Follow [the tooling guide](../local-tooling.md),
verify `java -version` and the installed CLI's `--version`, and set
`MESSAGING_PDF_VALIDATOR` in `.env` to the actual executable. Restart the API
and local stack so the API receives the setting.

The local stack launcher reports a missing/non-executable validator or a
failing version probe with the installation command and affected feature.
Startup continues: login, Inbox, Outbox, Drafts and other application features
remain usable. Capture still fails closed if either PDF/A-2u or PDF/UA-1
validation cannot succeed; no partial record is committed. The startup check
is an availability reminder, not PDF conformance verification.

Implementation: `tools/check_local_pdf_validator.py` runs from
`run-local-stack.sh` after `.env` loading and before service startup/reuse.
Verification: eight database-free tests cover missing/empty configuration,
configured and PATH executables, runtime failure, timeout, execution errors
and a non-blocking CLI exit from a different working directory. Shell syntax
and diff checks passed. No test stack or database was launched.
