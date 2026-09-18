# Navigation breadcrumbs

Every authenticated page displays a compact navigation-history breadcrumb above
its title. It records primary pages and dedicated entity pages visited during
the current signed-in browser session. Dialogs, searches, filters, tree
expansions, and other interactions within a page do not create separate
entries.

Choosing an earlier entry restores that page and removes the abandoned forward
branch. Listing pages restore their search mode, search text, status filter, and
whether results had been loaded. Organization-browser state continues to use
its dedicated signed-in session state. Current entity data is retrieved again
from the API rather than treated as part of the navigation history.

The trail retains at most 20 entries. Up to five are shown directly; longer
trails place older intermediate entries in an accessible ellipsis menu.
Consecutive visits to the same logical page collapse into one entry, so refresh,
edit completion, and ordinary re-rendering do not add duplicates.

Record, Aggregation, Organization Unit, Role, and User detail-page Back buttons
use the same trail. If no preceding entry exists, they return to their
corresponding listing page.

The trail survives browser refresh within the authenticated session. It is
cleared at sign-out, session rejection, or explicit sign-in as another user.
It is browser-local presentation state, is not stored in PostgreSQL, and does
not create event-history entries.

Structural breadcrumbs remain separate. For example, the aggregation hierarchy
inside Aggregation Detail still communicates ancestry, while the page-level
breadcrumb communicates how the user reached that page.

See [`../specs/persistent-navigation-breadcrumbs.md`](../specs/persistent-navigation-breadcrumbs.md)
for the complete semantics and acceptance criteria.
