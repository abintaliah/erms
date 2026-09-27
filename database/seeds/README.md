# ERMS seed data

Seed scripts create optional reference, demonstration, or load-test data. They
are not schema migrations and must not insert rows into `schema_migrations`.
Apply them explicitly with `psql`, after the canonical schema and required
migrations have been installed.

Every event-history row produced by a canonical seed uses source `seeding`.
The source `migration` is reserved exclusively for genuine database upgrades.

## Generated Arabic UI-translation drafts

Apply the approved Phase 6 Arabic draft artifact explicitly with:

```bash
PYTHONPATH=. backend/services/api/.venv/bin/python \
  database/seeds/004_seed_generated_arabic_ui_translations.py \
  --database-url "$DATABASE_URL"
```

The utility accepts `--database-url` and otherwise falls back to `DATABASE_URL`.
It synchronizes the application-owned message
definitions, validates every generated translation, and replaces only untouched
Arabic `source_copy` rows. It is idempotent: later runs protect generated,
manual, imported, reviewed, and published values. It reports stored, protected,
and failed counts and exits unsuccessfully if any artifact entry fails. The API
does not invoke this seed during startup.

The seed program is deliberately independent of individual translation keys.
During future Agentic-AI WebUI development, the agent updates the authoritative
English catalogue and `frontend/webui/i18n/messages.ar.generated.json` in the
same code change: adding Arabic drafts for new keys, regenerating materially
changed entries, and removing entries for safely removed definitions. It also
refreshes provenance and hashes and runs completeness, stale-key, placeholder,
terminology, and Arabic-quality checks. Operators rerun this unchanged utility
to apply newly eligible drafts; it never silently overwrites existing generated
or administrator-managed database values.

The canonical classification-scheme seeds are:

- `002_seed_ewa_functional_classification_scheme.sql`, formerly introduced by
  migration 021; and
- `003_seed_general_classification_scheme.sql`, formerly introduced by
  migration 024.

The historical 021 and 024 files remain under `database/migrations/` because
existing databases may already record those exact migration identifiers.
Keeping them preserves deployed migration history. New environments should
use the canonical seed scripts above when optional example schemes are wanted.

Both canonical scripts are transactional, reject an existing scheme with the
same code or title, and do not read or write `schema_migrations`.

## USCR-SHJ Arabic demonstration records

After importing `examples/fileplans/mutamathilah.xml`, create the deterministic
Arabic demonstration dataset with:

```bash
backend/services/api/.venv/bin/python database/seeds/seed_uscr_shj_arabic_demo.py \
  --database-url "$DATABASE_URL"
```

The utility creates 400 classified aggregations, 1,600 records, and 3,199
stored digital components selected by subject from the bilingual sample corpus.
Exactly 40 aggregations and 160 records are Vital. The operation is
transactional, uses audited `seeding` provenance, and is idempotent only when
the existing reserved dataset exactly matches the deterministic plan and its
source manifest. Partial or conflicting data causes a safe failure.

Aggregation numbers use
`<terminal-classification-code>/<2026>/<classification-local-serial>`. Record
numbers use `<parent-aggregation-number>.<aggregation-local-serial>`. Databases
that received version 1 of this seed can be reconciled transactionally with:

```bash
backend/services/api/.venv/bin/python \
  database/seeds/reconcile_uscr_shj_demo_numbering.py \
  --database-url "$DATABASE_URL"
```

## GCS classification-tree load data

`001_seed_gcs_aggregation_tree_load_data.sql` creates a deterministic dataset:

- 100 root aggregations distributed across GCS terminal classifications other
  than `GCS-01.01.01`;
- 300 records distributed across those aggregations;
- 75 root aggregations governed specifically by `GCS-01.01.01`; and
- 100 records distributed across those focused aggregations.

The script is transactional and refuses to run when its reserved
`GCS-SEED-` identifiers already exist.

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/seeds/001_seed_gcs_aggregation_tree_load_data.sql
```
