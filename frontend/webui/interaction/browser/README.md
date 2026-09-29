# Classification transfer browser checks

Start `backend/services/api/.venv/bin/python tools/test_scheme_transfer.py --preview`
from the repository root. This creates disposable databases, initializes the
canonical schema and published language fixtures, runs the API suite, and starts
the preview at `http://127.0.0.1:18080/`. Use only this preview for these checks.
The runner owns server shutdown and database cleanup; finish with Ctrl-C and
verify both database-drop messages.

Sign in using the disposable credentials in the test fixture. Load
`classification_transfer.js` into the CUA runtime and create
`checks = classificationTransferChecks(tab)` with the documented browser tab.
Run each phase separately to allow visual inspection:

1. `checks.list()` checks Import placement and filters to `UI-TRANSFER`.
2. `checks.choose(path)` uploads the checked-in `scheme.json` fixture.
3. `checks.imported()` checks the refreshed list, retained filter and draft.
4. `checks.choose(path)` uploads the matching `scheme.csv` fixture, then
   `checks.duplicate()` checks rejection and retained page state.
5. `checks.details()` checks export placement, formats and registry languages.
6. Choose a language, then run `checks.geometry('ltr')`. Repeat at a narrow
   viewport. Use normal Preferences controls to switch to Arabic, reopen the
   Word dialog and repeat with `checks.geometry('rtl')`.
7. Exercise each download control and confirm successful authenticated responses.

Repeat on a fresh preview with CSV first and JSON second. Fixture paths are
under `backend/services/api/scheme_transfer/tests/fixtures/`. Restore the browser
viewport before closing the preview. Never point this workflow at a persistent
database.

For a genuinely empty list, start a separate preview with
`--preview -k test_anonymous_transfer_denied`. That case initializes users and
published languages but creates no schemes. Verify Import beside Add without a
filter, navigate Dashboard → Classification schemes three times, then import.

For paging, seed at least 50 additional schemes in the disposable destination
with event source `seeding`. Run `paged()`, import a distinct package, wait for
the dialog to close, then run `retainedPages()`.

For timing checks, hold `LOCK TABLE classification_schemes IN SHARE MODE` in a
separate transaction connected explicitly to the runner's disposable destination.
Upload a valid package with a new code and run `pending()`. Navigate to Dashboard,
release the lock with rollback, and run `abandoned()`. Confirm the server log
contains only one import request, then revisit/filter to the imported code to
check freshness. Always release the gate, including after a failed check.

Repeat with a distinct `UI-IDENTITY` package: while the request is pending, cancel
the dialog, sign out, and sign in as a separately seeded disposable viewer with
no assigned roles. Release the gate, open the account menu, and run `viewer()`.
Verify no previous-user notification, import control, or navigation appears.
The browser uses normal login controls; never replace cookies or application
state to simulate identity changes. Test passwords remain disposable fixture data.
