# Saved-search localization

The saved-search action label resolves its existing message key inside the
button's owning NiceGUI slot. Restoration callbacks can otherwise render outside
the page slot and fall back to an ambient English catalogue. This applies to both
Save search and Update saved search.

Saved-search responses include `owner.localized`, using the viewer's preferred
language and the standard entity translation fallback. Canonical owner fields
remain unchanged. The open-search header and picker use `owner.localized.name`
before the canonical name. Language is resolved once per list response; owner
translations use the existing owner query, without additional per-item requests
or a new cache.

Verification: `test_saved_search_localization.py` exercises the actual refresh
function with a real NiceGUI button and an English ambient context, repeatedly
switching between saved and new-search states. It reproduced the English fallback
before the fix. The localization tests passed (22 tests). Saved-search API tests
passed (7 tests), including Arabic owner projection and English fallback, in a
fresh disposable database initialized from `database/schema.sql` and dropped
afterward. The full signed-in browser navigation sequence was not replayed.

No translation keys or artifacts changed, and no database migration is needed.
After restarting the API and WebUI, reopen an already-loaded saved search to
fetch its owner's localized projection.
