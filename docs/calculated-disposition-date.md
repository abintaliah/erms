# Calculated disposition date

Aggregation details show a calculated disposition date below the retention
stages and above the classification/instructions footer. Only the date and
closure date appear in the new block; the existing stages already show both
retention periods.

The governing root is the disposition unit. Its closure date, converted to the
user's working timezone, plus the sum of the effective current and intermediate
retention years determines the displayed calendar date. February 29 becomes
February 28 in a non-leap target year. Child pages show the root's date. An open
or unavailable root produces no date block. This display neither authorizes
disposition nor bypasses holds or any other safeguard.

The implementation uses already-loaded ancestor and effective-rule data. It
adds no requests, caches, background tasks, schema changes, or privileges.
Each normal details-page render calculates from that render's current data.

Verification: 11 focused calculation tests cover ordinary and zero periods,
leap years, the working-timezone date boundary, and missing/invalid inputs.
The actual NiceGUI date component was inspected in a temporary standalone
browser preview in English and Arabic. Full authenticated aggregation-page
navigation was not replayed. Catalogue reference checks and Python compilation
pass.

Localization: one new key,
`webui.open_aggregation.retention.calculated_disposition_date`, is added to the
English manifest and canonical Arabic artifact. Existing Arabic wording and
provenance are preserved; no administrator export was promoted. The new Arabic
draft requires review/publication. `entity_metadata.field.date_closed` is reused.
No persistent database was changed by this implementation.
