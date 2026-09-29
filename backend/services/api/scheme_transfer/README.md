# Classification scheme transfer implementation

The product contract is `specs/classification-scheme-import-export.md`.
Acceptance is tracked there; passing a subset does not establish completion.

## API and transaction boundary

- `POST /api/v1/classification-schemes/import?format=json|csv` takes one multipart
  `file`, returning HTTP 201 with `id`, `code`, and `date_published: null`.
- `GET /api/v1/classification-schemes/{scheme_id}/export?format=json|csv|docx`
  returns an authenticated attachment. DOCX requires an explicit `language`
  matching an enabled supported-language tag.
- Both routes require `classifications.administer`, including when translations
  are present. They do not grant independent entity-translation editing rights.
- Import uses the request's existing database transaction. Parsing/checksum and
  compatibility checks precede insertion. Local IDs come from destination
  sequences; dependency-order insertion restores relationships. Unique indexes
  arbitrate concurrent imports. Deferred constraints run before returning.
  Failures roll back the entire request, including transactional history.
- Exports run in a read-only REPEATABLE READ transaction. Word dependencies are
  imported only for Word requests. No export is built on the browser.

## Provenance storage and triggers

Existing immutable `event_history` CREATE records hold the persistent mapping.
`metadata.classification_scheme_import` contains the source manifest, entity
kind, source entity fields, and source scheme identity. Each CREATE record's
`entity_id`/`after_state.id` identifies the destination entity. This also applies
independently to explicit rules. Source publication remains in the source
scheme snapshot, while the inserted scheme has NULL `date_published`.

There is no new event action, source enum, table, privilege, or migration.
Existing `api`/`web_ui` sources and the actual authenticated importing actor
remain in force. Source actor IDs remain provenance only. INSERT retains the
explicit source timestamps and versions; the existing timestamp/version
triggers apply on subsequent UPDATE. Existing first-use immutability and
publication/deletion governance remain effective. Source event history is
never replayed. Ordinary create/update APIs retain their current field rules.

## Build provenance and resource bounds

Package deployments must set `WATHIQ_APPLICATION_REVISION` to the full lowercase
40- or 64-character Git object ID captured at build time. Source deployments
fall back to `git -C <repository root> rev-parse HEAD`. Missing/malformed revision
fails export rather than inventing a value. The revision cache is process-local,
keyed by the deployed process, immutable until restart, and contains no user or
language data; failures are not cached. Redeploy/restart after changing the
revision. A SHA does not describe uncommitted modifications.

`source.schema_version` is `migrations:` followed by sorted applied migration
versions when the ledger has rows. For a canonical empty-database install with
an empty ledger, it is `canonical-sha256:` plus the bundled `database/schema.sql`
SHA-256. This is a release provenance identifier, not a live schema-drift audit.

The shared package limit is 32 MiB and 10,000 classifications. Oversize work is
rejected explicitly, never truncated. Traversal is iterative, with no separate
business depth limit. Export checks source size/count before graph materializing
and encoded size before returning. Configure the deployment reverse proxy's
request-body limit to bound multipart ingress before framework spooling.

The JSON Schema validator caches one immutable packaged schema per process;
restarting on deployment invalidates it. It has no database/user/language data.
Word labels are read from published catalogues inside the export snapshot;
no extra catalogue cache is introduced. UI result guards include workspace
identity and navigation revision, so abandoned results do not update a later
visit or another identity.

## Verification

Run `backend/services/api/.venv/bin/python tools/test_scheme_transfer.py`.
The runner creates unique disposable source/destination PostgreSQL databases,
loads `database/schema.sql` alone, installs/publishes Arabic and an additional
French test catalogue, runs tests, and drops both databases in `finally`.
English uses the canonical source catalogue. All fixtures and application
processes receive only disposable connection strings. `--preview` starts API
and WebUI on ports 18000/18080 after passing tests and owns them until Ctrl-C;
it then terminates the servers and drops both databases. Creation/cleanup
failures fail the run. Never run this test directory against a persistent DB.

`TRANSFER_QA_DIR` saves generated English/Arabic/French documents for visual QA.
This includes the empty, broad, deep, multiple-root, deactivated and long-text
hierarchy fixtures. Word paragraphs use logical `w:start` indentation so RTL
hierarchies indent from the right; physical `w:right` did not render correctly
in the acceptance renderer. The maximum indentation is capped while explicit
depth and parent codes remain available at every level.
French catalogue text is deliberately marked test wording (`FR ...`), not a
maintained French translation artifact. Checked-in `tests/fixtures/scheme.json`
and `scheme.csv` reconstruct the same valid package and digest.

Frontend interaction checks use NiceGUI's test user and bounded fake APIs; they
supplement real-browser verification and do not replace database/browser E2E
acceptance. Run them with `--asyncio-mode=auto`.

The transfer dialogs use standard NiceGUI dialog, upload, select, row, and button
components. Live RTL inspection showed inherited `direction: rtl` was already
correct, but the application's broad `.row { flex-direction: row-reverse }`
reversed the field and button rows a second time. NiceGUI row/select APIs expose
no control-level RTL switch. The narrowly scoped transfer-dialog CSS restores
normal row flow and the field label's start edge without changing other pages.

Word display exports use native paragraph/table/run direction properties without
inserting Unicode direction controls. They use Changa 10, a 13.5 × 8.5-inch
landscape page and a fixed 12.4-inch table. Effective current/intermediate
retention periods and final disposition follow the title. Babel formats display
dates with localized month names and an explicit UTC timezone; transfer dates
remain unchanged. Changa must be available to the document viewer. For the
bundled headless renderer, supply a FONTCONFIG_FILE that includes the installed
Changa font directory, then verify PDF font names with pdffonts.
