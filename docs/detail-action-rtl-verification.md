# Detail action alignment — 29 September 2026

The approved direction rule is reading-start alignment for detail action groups:
left in English, right in Arabic, including the beginning of every wrapped line.

## Cause and implementation

Live record-page inspection found inherited `direction: rtl` combined with the
legacy global `.row { flex-direction: row-reverse }` rule. A 296px action row
began its buttons at x=74, its left edge, instead of its right edge at x=370.
NiceGUI Row exposes `wrap` and `align_items` but no direction option. Alignment
alone would not correct order, and a fixed grid would lose variable-width button
wrapping. The existing classification workspace already uses a scoped direction
correction for this problem.

`frontend/webui/app.py` now scopes logical row direction to record controls,
organization-unit/role/user action panels, aggregation actions and hold controls,
and explicitly marked credential/text-indexer/held-item action groups. Hold and
classification action panels retain their already-correct group direction and
share the corrected button icon treatment. Quasar's physical `on-left`/`on-right`
icon margins are mirrored only inside these groups: inspection found the icon
touching its label with the 6px gap on the outside before this correction.

Identity-header Back/Favourite/Preview controls are outside these selectors.
No API calls, permissions, callback behavior, catalogue wording, translation
keys, or database schema changed.

## Evidence

- Browser checks on record, aggregation, organization-unit, role, user, and
  classification details: visible Arabic action groups use logical `row` order
  and their first button ends at the right edge of the group.
- English record, aggregation and user controls remain left aligned.
- Arabic user and aggregation pages and English user details checked at 714px:
  no horizontal document overflow; groups retain reading-start alignment.
- Button icon spacing measured at 6px between icon and label in Arabic.
- All 38 existing NiceGUI interaction tests passed.
- Verification uses a uniquely named disposable database initialized from
  `database/schema.sql`; no persistent database is used for tests.

Text-indexer credential and Hold action selectors were reviewed in source; live
checks above cover the shared direction/spacing rules rather than exercising
credential mutations or Hold operations.
