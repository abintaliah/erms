# Classification Scheme Import and Export

**Status:** Implemented and verified — approved product decisions retained
**Prepared:** 29 September 2026
**Revision:** 0.17 — successful classification scheme export event history
**Implementation state:** API/codecs/Word/UI implemented; prior acceptance evidence recorded below; IE-14 export auditing implemented and verified; Arabic draft wording awaits human review

## 1. Purpose and governing specifications

Transfer a complete classification scheme between Wathiq databases without
silently losing scheme or classification data, and produce a readable Word
representation. Export supports three formats: JSON, CSV, and MS Word (.docx).
Import supports JSON and the exported CSV format. The original reference to “2 formats” is interpreted
as the three explicitly named formats.

This draft supplements, and does not override, the approved
[classification subsystem](classification-scheme-subsystem.md),
[security subsystem](security-and-authorization-subsystem.md),
[internationalization specification](internationalization-and-user-preferences.md),
[WebUI performance contract](../docs/webui-performance.md), and
[WebUI design language](../docs/webui-design-language.md).

Requirements below describe the proposed implementation contract. Unresolved
product choices are explicitly listed in section 12; drafting them is not
approval to implement them.

## 2. Scope and preservation boundary

**IE-01:** Each export contains exactly one scheme, all its classifications
(including deactivated classifications), their hierarchy, all explicit
classification retention rules, and all stored entity translations.

Exports use one consistent database snapshot. They must not depend on the
currently visible page, tree expansion, filters, or UI language. Every stored
translation is exported, not merely the localized display value.

The approved transfer boundary is the current state of the scheme and its
owned entities. Linked aggregations, records, aggregation retention overrides,
user selection preferences, users, roles, and language configuration are not
transferred. Immutable source event history is excluded, as approved under D1.

**IE-02:** Preserve the following fields in the transfer package and source
provenance, subject to the destination publication-state rule in IE-12.
Names in this table are canonical
database field names. All application-defined JSON property names and CSV
column and field names use snake_case. Translation language tags retain their
stored spelling. Structural groupings and field mappings are defined below.

| Entity | Fields |
| --- | --- |
| Scheme | `id`, `code`, `title`, `description`, `authority`, `scope_note`, `edition`, `date_created`, `date_updated`, `date_published`, `date_deactivated`, `date_first_used`, `version`, `translations` |
| Classification | `id`, `classification_scheme_id`, `parent_classification_id`, `code`, `title`, `description`, `authority`, `scope_note`, `keywords`, `is_terminal`, `date_created`, `date_updated`, `date_deactivated`, `date_first_used`, `version`, `translations` |
| Classification retention rule | `id`, `classification_id`, `current_period_years`, `intermediate_period_years`, `final_disposition`, `instructions`, `date_created`, `date_updated`, `version` |

Source numeric IDs are provenance, not destination primary keys. The enclosing
scheme and classification express ownership; parent codes express hierarchy.
Allocate new destination IDs and remap all relationships. Source ID provenance
must remain recoverable after import through a persisted source-to-local
provenance mapping, as approved under D2. Preserve original dates, first-use
markers, and versions except for the destination publication date under IE-12.
Imported first-use markers retain their governance effect even without linked
records. Document the storage and trigger implementation before coding.

Export explicit retention rules only. A missing owned rule remains missing;
do not turn effective inherited rules into explicit child rules. Derived
status, hierarchy depth, paths, counts, and effective rules are recomputed.

## 3. Shared interchange value rules

**IE-03:** JSON and CSV encode the same transfer model, with these rules:

- UTF-8; preserve Unicode text, embedded newlines, whitespace, and empty text.
- Preserve null separately from empty text, absent translation fields, and an
  empty translations object.
- Dates are ISO 8601 UTC timestamps with six fractional-second digits and `Z`.
  Preserve the instant and PostgreSQL microsecond precision.
- Integers use decimal notation without grouping. Booleans are `true` or
  `false`. Codes are text, retaining leading zeros and exact spelling.
- Scheme uniqueness and classification-code uniqueness follow the existing
  PostgreSQL case-insensitive constraints. Export never rewrites code case.
- Version 1.0 defines a closed vocabulary. Reject unknown versions, fields,
  duplicate fields, and unsupported values rather than silently ignore them.
- Retention disposition values are exactly `destruction`,
  `transfer_to_external_archive`, `selective_preservation`, and
  `retain_as_local_archives`.
- An unsupported or disabled destination translation language causes a clear
  rejection. Import does not silently drop translations or enable languages.
- If a value cannot be represented by the selected format, export fails
  explicitly rather than replacing or deleting characters.

## 4. JSON package

### 4.1 Envelope and manifest

**IE-04:** Export a `.json` file with media type `application/json`, encoded as
UTF-8 without a BOM. Its root is an object with exactly four required properties:
`package_type` (the literal `classification_scheme_export`), `format_version`
(the string `1.0`), `manifest`, and `data`. `data` contains exactly one `scheme`.
The implementation shall provide a versioned local JSON Schema and validate
without retrieving remote schemas. Object member order has no semantic meaning.

The manifest is required because checksum validation is required for import.
All properties listed below are required; only `display_name` is nullable.
Dotted paths indicate nested objects, not literal dotted property names.

| Manifest property | Type and meaning |
| --- | --- |
| `export_id` | UUID string identifying this export operation |
| `exported_at` | Export timestamp string |
| `exported_by.source_user_id` | Source user ID as a decimal string; provenance only |
| `exported_by.username` | Exporter username snapshot string |
| `exported_by.display_name` | Display-name snapshot string or null |
| `source.application` | String, `Wathiq` |
| `source.application_revision` | Full Git commit SHA of the exporting application as a lowercase hexadecimal string |
| `source.database_name` | Actual source database name string |
| `source.schema_version` | Canonical schema/migration release identifier string |
| `counts.classifications` | Nonnegative integer |
| `counts.retention_rules` | Nonnegative integer |
| `checksum` | Object with the fixed properties and digest from section 5 |

Do not include credentials, connection strings, session tokens, or database
passwords in provenance.

For now, `application_revision` replaces `application_version`; a separate
application release number is not required. Capture the full Git commit SHA
from the application source checkout at build/package time and supply it with
the running application. For a source-checkout deployment, resolve that
checkout's HEAD. Do not use an abbreviated SHA, branch name, or a commit from
an unrelated working directory. A commit SHA identifies committed source; it
does not attest to uncommitted local modifications.

This metadata does not require a database column or migration. Keep it separate
from `schema_version`, which identifies the source database schema. The exact
mapping from applied migrations to `schema_version` must be documented before
implementation. The importer uses `format_version` to interpret the package;
it must not require the destination application's commit to match the source.

### 4.2 Entity representation

Every property listed here is required, including nullable properties.

- Scheme: `source_id`, `code`, `title`, `description`, `authority`, `scope_note`,
  `edition`, `date_created`, `date_updated`, `date_published`, `date_deactivated`,
  `date_first_used`, `version`, `translations`, `classifications`.
- Classification: `source_id`, `code`, `parent_code`, `title`, `description`,
  `authority`, `scope_note`, `keywords`, `is_terminal`, `date_created`,
  `date_updated`, `date_deactivated`, `date_first_used`, `version`, `translations`,
  `retention_rule`.
- Owned retention rule: `source_id`, `current_period_years`,
  `intermediate_period_years`, `final_disposition`, `instructions`,
  `date_created`, `date_updated`, `version`.

Dates use the canonical database field names directly, without a `dates`
wrapper. Nullable database fields use JSON `null`; empty text uses `""`.
`source_id` maps to the source database `id`. Ownership is represented by the
enclosing scheme/classification, and `parent_code` is a string referencing a
classification in the same package, or null for a root. A missing owned rule
is represented by `"retention_rule": null`. Booleans use JSON boolean values.
Retention periods are nonnegative JSON integers within PostgreSQL integer range.

All PostgreSQL bigint IDs and version values are positive decimal **strings**
matching `[1-9][0-9]*`, bounded by PostgreSQL bigint maximum
`9223372036854775807`. This includes `source_id`, `source_user_id`, and `version`.
Do not convert them through floating-point numbers: their full range exceeds
JSON consumers' commonly supported exact integer precision. Manifest counts
are JSON integers in the safe range 0 through 9007199254740991. No field in
this version uses floating-point values.

`translations` directly preserves the stored JSON object: null for SQL NULL,
`{}` for an empty object, or an object keyed by stored language tags. Each
language value is an object containing its stored `title` and/or `description`
strings. A missing translated field remains absent. Do not synthesize fallback
translations, stringify the object, or wrap it in language-entry arrays.

`classifications` is a flat array of classification objects, or `[]` for an
empty scheme. For deterministic readable output, traverse roots and descendants
depth-first, ordering siblings by code using the existing C-collation ordering.
Import resolves parent references independently of array position. A differently
ordered array is acceptable with a valid checksum calculated for that order.

### 4.3 Example

This example includes all entity fields. The example commit SHA, schema identifier, and
checksum digest are illustrative placeholders; it is not a valid integrity-test fixture.

```json
{
  "package_type": "classification_scheme_export",
  "format_version": "1.0",
  "manifest": {
    "export_id": "98f78fd4-854b-4ea2-a236-ac04efb50cc0",
    "exported_at": "2026-09-29T10:30:00.000000Z",
    "exported_by": {
      "source_user_id": "42",
      "username": "records.admin",
      "display_name": "Records Administrator"
    },
    "source": {
      "application": "Wathiq",
      "application_revision": "0123456789abcdef0123456789abcdef01234567",
      "database_name": "wathiq_source",
      "schema_version": "SCHEMA_IDENTIFIER"
    },
    "counts": {
      "classifications": 2,
      "retention_rules": 1
    },
    "checksum": {
      "algorithm": "SHA-256",
      "canonicalization": "RFC8785",
      "scope": "package_excluding_checksum",
      "encoding": "hex",
      "value": "CHECKSUM_HEX"
    }
  },
  "data": {
    "scheme": {
      "source_id": "12",
      "code": "GCS",
      "title": "General Classification Scheme",
      "description": "Administrative records classification.",
      "authority": "Records Management Department",
      "scope_note": null,
      "edition": "2026",
      "date_created": "2026-01-01T08:00:00.000000Z",
      "date_updated": "2026-01-01T08:00:00.000000Z",
      "date_published": "2026-01-05T08:00:00.000000Z",
      "date_deactivated": null,
      "date_first_used": null,
      "version": "3",
      "translations": {
        "ar": {
          "title": "خطة التصنيف العامة"
        }
      },
      "classifications": [
        {
          "source_id": "100",
          "code": "01",
          "parent_code": null,
          "title": "Administration",
          "description": null,
          "authority": null,
          "scope_note": null,
          "keywords": null,
          "is_terminal": false,
          "date_created": "2026-01-01T08:00:00.000000Z",
          "date_updated": "2026-01-01T08:00:00.000000Z",
          "date_deactivated": null,
          "date_first_used": null,
          "version": "1",
          "translations": null,
          "retention_rule": {
            "source_id": "200",
            "current_period_years": 2,
            "intermediate_period_years": 5,
            "final_disposition": "destruction",
            "instructions": null,
            "date_created": "2026-01-01T08:00:00.000000Z",
            "date_updated": "2026-01-01T08:00:00.000000Z",
            "version": "1"
          }
        },
        {
          "source_id": "101",
          "code": "01.01",
          "parent_code": "01",
          "title": "Administrative correspondence",
          "description": null,
          "authority": null,
          "scope_note": null,
          "keywords": null,
          "is_terminal": true,
          "date_created": "2026-01-01T08:00:00.000000Z",
          "date_updated": "2026-01-01T08:00:00.000000Z",
          "date_deactivated": null,
          "date_first_used": null,
          "version": "1",
          "translations": null,
          "retention_rule": null
        }
      ]
    }
  }
}
```

## 5. Shared package integrity contract

**IE-05:** Require one `manifest.checksum` object containing exactly `algorithm`,
`canonicalization`, `scope`, `encoding`, and `value`. The first four have the
fixed values shown in the example; `value` is 64 lowercase hexadecimal digits.
Reject alternative algorithms, scopes, or extra checksum properties.

For CSV, first reconstruct the typed JSON package using section 6.4. The same
checksum object and hash scope apply to both formats; do not hash raw CSV bytes.

Algorithm for the JSON package:

1. Parse strict JSON, rejecting duplicate property names at every depth before
   a parser can discard them. Reject invalid Unicode, comments, trailing commas,
   non-finite numbers, trailing content, and numeric values outside this contract.
2. Validate the package structure and types without coercing values, inserting
   defaults, resolving translations, or changing dates or publication state.
3. On a copy of the parsed root object, remove only `manifest.checksum`.
4. Canonicalize the remaining root object using RFC 8785 JCS and hash its UTF-8
   bytes with SHA-256.
5. Compare the resulting lowercase hexadecimal digest with the declared value
   before any database mutation.

This protects the envelope, provenance, counts, and scheme data. The omitted
checksum metadata is validated against fixed constants. Use a conformant JCS
implementation rather than assuming ordinary sorted-key JSON serialization
is equivalent. Reference: [RFC 8785 — JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785).

Formatting whitespace and object-member order do not affect the digest.
Array order and string contents do; do not trim or normalize Unicode text.
Bigint IDs/versions remain strings during hashing. Exports may be pretty-printed
without changing the digest. Test equivalent string escapes and object order,
changed array order, and source text changes with the selected implementation.

A checksum establishes integrity, not authenticated authorship. A digital
signature and trust infrastructure are outside this proposed contract.

## 6. CSV structure

### 6.1 Single-file typed-row format

**IE-06:** Export one `.csv` file containing a fixed header and typed rows.
This avoids requiring multiple companion files to reconstruct one scheme.
CSV is a lossless interchange representation, not a spreadsheet display report.
Import accepts this exact versioned CSV format and reconstructs the shared
package before validation. Generic spreadsheets and other CSV layouts are not
accepted.

Use comma delimiters, double-quote escaping (double an embedded quote), CRLF
record separators, and UTF-8 without a BOM. Quote fields containing commas,
quotes, CR, or LF. Quoting does not change the represented field value.

Columns, in this exact order:

```text
format_version,row_type,scheme_code,classification_code,parent_code,source_id,field_name,language_tag,value,value_state
```

| Column | Contract |
| --- | --- |
| `format_version` | `1.0` on every row |
| `row_type` | `manifest`, `scheme`, `classification`, `retention_rule`, or `translation` |
| `scheme_code` | Exact scheme code on every row |
| `classification_code` | Owner code for classification/rule rows and classification translations; empty otherwise |
| `parent_code` | Exact parent code on classification rows; empty for roots and other row types |
| `source_id` | Source entity ID for scheme/classification/rule rows and translation owner; empty for manifest |
| `field_name` | One field from the closed vocabulary below |
| `language_tag` | Present only for translation rows |
| `value` | Field's complete serialized value, without display localization |
| `value_state` | `value`, `null`, or `empty_object` |

Each row carries one field, so there is no very wide sparse table and no JSON
hidden inside text cells. Repeated owner columns make each row attributable.
All owner metadata on rows for the same entity must agree.

`value_state=value` with an empty value means an empty string.
`value_state=null` requires an empty value and means SQL NULL.
`value_state=empty_object` requires an empty value and is allowed only for a
`translations` field, representing `{}`.

### 6.2 Field vocabulary and relationships

- `manifest` fields: `export_id`, `exported_at`, `exported_by_source_user_id`,
  `exported_by_username`, `exported_by_display_name`, `source_application`,
  `source_application_revision`, `source_database_name`, `source_schema_version`,
  `classification_count`, `retention_rule_count`, `checksum_algorithm`,
  `checksum_canonicalization`, `checksum_scope`, `checksum_encoding`,
  `checksum_value`.
- `scheme` fields: `title`, `description`, `authority`, `scope_note`, `edition`,
  `date_created`, `date_updated`, `date_published`, `date_deactivated`,
  `date_first_used`, `version`, `translations`.
- `classification` fields: `title`, `description`, `authority`, `scope_note`,
  `keywords`, `is_terminal`, `date_created`, `date_updated`, `date_deactivated`,
  `date_first_used`, `version`, `translations`, `has_retention_rule`.
- `retention_rule` fields: `current_period_years`, `intermediate_period_years`,
  `final_disposition`, `instructions`, `date_created`, `date_updated`, `version`.
- `translation` fields: `title` or `description`.

For a nonempty translations object, its owner's `translations` row has
`value_state=value` and `value=present`; translation rows carry all actual
language/field pairs. Null or empty objects prohibit translation rows. Missing
translation field rows represent absent object keys, not null values.

`has_retention_rule` is a structural boolean: true requires one complete owned
rule; false prohibits rule rows. Parent and scheme foreign keys are represented
by owner columns; source IDs preserve the original numeric identities.

All listed scalar fields occur exactly once per applicable entity. Duplicate
owner/field rows or owner/language/field translation rows are invalid. Class
codes cannot be blank, making an empty classification owner unambiguously a
scheme translation. Source rule IDs may overlap class IDs because row type
distinguishes entity identity.

Order manifest rows first, scheme rows next, then classifications in the JSON
traversal order. Place each entity's translations and owned rule after its
scalar rows. Within each group use the field order above; sort language tags
lexicographically. Relationships must be recoverable without relying on order.

CSV carries the complete provenance and checksum as manifest rows. Map
`export_id` and `exported_at` directly to `manifest`; map `exported_by_*` into
`manifest.exported_by`, `source_*` into `manifest.source`,
`classification_count` to `manifest.counts.classifications`, and
`retention_rule_count` to `manifest.counts.retention_rules`. Map `checksum_*`
into the five properties of `manifest.checksum`. Their constants are identical
to section 5, including `checksum_scope=package_excluding_checksum`.

Every listed manifest field occurs exactly once. Only
`exported_by_display_name` permits `value_state=null`; every other manifest
field has `value_state=value` and must satisfy its JSON type and value rules.
No separate manifest file is required.

### 6.3 Abbreviated example

This excerpt illustrates values and relationships, not a complete export.

```csv
format_version,row_type,scheme_code,classification_code,parent_code,source_id,field_name,language_tag,value,value_state
1.0,manifest,GCS,,,,source_database_name,,wathiq_source,value
1.0,manifest,GCS,,,,checksum_algorithm,,SHA-256,value
1.0,manifest,GCS,,,,checksum_canonicalization,,RFC8785,value
1.0,manifest,GCS,,,,checksum_scope,,package_excluding_checksum,value
1.0,manifest,GCS,,,,checksum_encoding,,hex,value
1.0,manifest,GCS,,,,checksum_value,,CHECKSUM_HEX,value
1.0,scheme,GCS,,,12,title,,General Classification Scheme,value
1.0,scheme,GCS,,,12,scope_note,,,null
1.0,scheme,GCS,,,12,translations,,present,value
1.0,translation,GCS,,,12,title,ar,خطة التصنيف العامة,value
1.0,classification,GCS,01,,100,title,,Administration,value
1.0,classification,GCS,01,,100,is_terminal,,false,value
1.0,classification,GCS,01,,100,has_retention_rule,,true,value
1.0,retention_rule,GCS,01,,200,current_period_years,,2,value
1.0,classification,GCS,01.01,01,101,title,,Administrative correspondence,value
1.0,classification,GCS,01.01,01,101,description,,,value
1.0,classification,GCS,01.01,01,101,has_retention_rule,,false,value
```

Do not prefix apostrophes or otherwise mutate values to accommodate spreadsheet
auto-formatting or formula interpretation. This CSV is for data interchange;
the Word export is the human-readable report. Spreadsheet applications must
load its columns as text to preserve codes and literal values.

### 6.4 CSV parsing and package reconstruction

**IE-13:** CSV import follows a strict, lossless mapping into the package in
section 4, then the shared checksum and atomic import rules in sections 5 and 7.

1. Decode strict UTF-8. Accept an optional initial UTF-8 BOM and either CRLF or
   LF record separators; do not alter newline characters inside quoted values.
   Parse CSV quoting before interpreting values. Reject malformed quoting,
   duplicate or unexpected headers, wrong column counts, and blank records.
   The header names and order must match section 6.1 exactly.
2. Require `format_version=1.0` and the same nonblank `scheme_code` on every
   row. Reject unknown row types, field names, and value states, inconsistent
   owner metadata, duplicate fields, and populated columns that the row type
   requires to be empty. Validate required fields and nullability without
   silently filling missing values.
3. Group rows by entity type and owner code. There must be exactly one scheme;
   each classification has one consistent `source_id` and `parent_code` across
   all its scalar rows. Each rule has one consistent source ID and existing
   classification owner. Translation rows must reference an existing owner and
   match its source ID. Enforce code uniqueness using the existing database
   semantics; parent references must use the exact exported spelling of a code.
4. Convert only fields defined as booleans or numeric integers: boolean text
   must be `true` or `false`; integer text must match `0|[1-9][0-9]*` and satisfy
   the field's bounds. Bigint IDs/versions remain validated decimal strings.
   Do not infer types from content, trim text, parse localized dates, evaluate
   formulas, or convert code strings to numbers.
5. Construct `package_type=classification_scheme_export`, `format_version=1.0`,
   and the manifest using section 6.2's mapping. Construct the scheme and owned
   entities using the row owner columns and field values. Empty root
   `parent_code` maps to null. Convert the structural `has_retention_rule` flag
   to an owned rule object or null; do not add that flag to the JSON package.
   Reconstruct translations from their marker and translation rows, preserving
   null, empty objects, absent translated fields, and exact stored language tags.
   Zero classification groups produces `classifications=[]`.
6. Validate the complete parent graph, including missing parents and cycles,
   then construct the classification array in root-first depth-first order.
   Sort roots and each parent's children by the unsigned UTF-8 bytes of their
   exact code, matching C-collation order in the UTF-8 source database. CSV row
   order does not determine array order. Do not sort by localized title or by
   a numeric interpretation of codes. Exporters for both formats use this order.
7. Validate the reconstructed package against the same local JSON Schema and
   domain rules as JSON import, and verify its checksum before mutation. Do not
   change publication state or any source field before this verification.

The CSV checksum is calculated by the exporter over the shared package before
flattening it into rows. Reconstructing those rows must reproduce the same
package. JSON and CSV representations of that same package, including export
ID and timestamp, therefore carry the same checksum; independently initiated
exports need not match. Reordering CSV rows, changing record separators outside
quoted fields, or changing equivalent CSV quoting does not affect the checksum.
Changing an actual value, including whitespace within text, does affect it.

Missing or invalid checksums are rejected. Do not offer a checksum bypass for
manually edited CSV files. The same size/resource limits, authorization, error
handling, and transactional guarantees apply to both import formats.

## 7. Atomic JSON and CSV import

**IE-07:** Import creates a new scheme. It never merges into, replaces, updates,
or repairs an existing scheme, even if its contents are identical.

**IE-12:** Every successfully imported scheme starts as a **draft, unpublished**
scheme in the destination: its `date_published` is SQL NULL. This applies even
when the source scheme was published or had a future publication date. Import
does not publish or schedule publication. Subsequent publication uses the
existing authorized publication workflow.

The exported source publication date remains intact in the package and must
be retained as source provenance after import; it must not become the
destination's publication date. This deliberate state change is an exception
to direct restoration of source lifecycle values, not loss of source metadata.
Do not modify the package before verifying its checksum. Apply the destination
publication-state rule only when constructing the imported scheme.

1. Authenticate and require `classifications.administer` under IE-11 before
   proceeding with the import. This covers the whole package, including translations.
2. Parse JSON safely or reconstruct the package from CSV under IE-13; validate
   the envelope, exact format version, checksum, field
   completeness, counts, data types, and translation representation.
3. Validate code uniqueness, source identity consistency, parent existence,
   same-scheme membership, absence of cycles, terminal/branch rules, effective
   retention coverage, dates, and all existing domain constraints.
4. Check destination compatibility, including supported enabled languages.
5. Start a transaction and recheck destination scheme-code uniqueness using
   the canonical case-insensitive database constraint. A preflight check alone
   is not sufficient for concurrent imports.
6. Insert the complete graph and explicit rules in a dependency-safe order,
   setting the destination scheme's `date_published` to NULL under IE-12 and
   retaining other lifecycle values as approved under D2. Satisfy all existing
   final-state database constraints; do not disable integrity enforcement.
7. Commit only when the complete package succeeds. Roll back every inserted
   entity and transactional history row on any failure.

**IE-08:** Reimport of an already-present scheme code, in either format or
across formats, fails without changing
any existing scheme data. Two concurrent imports of the same code produce at
most one committed scheme. Invalid checksums and malformed files cause no
application database writes. Failure reporting must not create partial imports.
PostgreSQL sequence gaps from rolled-back allocations are not data mutations
to existing entities and are not promised to be reversed.

Code-based duplicate detection applies while that code exists. A permanent
ban on reusing a code after authorized deletion would require an additional
registry and is not included in the proposed contract.

Errors identify the relevant entity code/field and cause without exposing SQL,
credentials, or internals. Resource limits must bound file parsing and memory
use without introducing a business hierarchy-depth limit; specific limits and
large-package handling must be documented and tested before release.

## 8. MS Word export

**IE-09:** Produce `.docx` with landscape orientation by default, on a
13.5-inch-wide by 8.5-inch-high page (8.5 × 13.5-inch stock). Use Changa at
10 points, including complex-script text and document headings. Set all script
font slots explicitly so Word does not substitute a theme font for Arabic.

Before generating the Word document, offer a language selector populated from
Wathiq's enabled `supported_languages`, including **English (LTR)** and
**Arabic (RTL)** and any languages supported and enabled in the future. Do not
hard-code a two-language list or infer direction from the language name.
All enabled choices must be available regardless of the current WebUI language.
Use the selected language tag and its configured `direction` (`ltr` or `rtl`)
to govern document language, generated headings and labels, paragraph direction
and alignment, table reading direction, and hierarchy indentation. Use the
existing language configuration and localization/fallback rules, including
appropriate fonts and formatting, rather than a separate export-language
registry. The following illustrate the initial choices:

| Option | Document formatting |
| --- | --- |
| English (LTR) | English headings and labels; left-to-right paragraphs and tables; hierarchy indentation from the left |
| Arabic (RTL) | Arabic headings and labels; right-to-left paragraphs and tables; hierarchy indentation from the right; Arabic-capable typography |
| Any other enabled supported language | Localized headings and labels using existing fallback rules; paragraph/table direction and indentation follow configured `direction`; fonts support the selected language |

Use the existing entity-localization and fallback rules for displayed entity
text in the selected language. This option does not machine-translate stored
content or remove the available translations required below. Mixed-language
text and literal codes must retain their correct reading order. Landscape
orientation and the same data coverage apply to every language option. The
server validates the requested language against enabled supported languages;
unsupported or disabled selections are rejected rather than silently replaced.

- A scheme-information table includes code, title, description, authority,
  scope note, edition, dates, version, and available translations; include an
  export provenance block with exporter, time, and source database.
- Every root classification starts a separate table containing itself and all
  descendants in depth-first order. Do not combine unrelated roots.
- Columns in reading order: code, level, title, current retention period,
  intermediate retention period, final disposition action, metadata, and
  remaining retention-rule information. The three new retention columns follow
  the title and show the effective rule, including inherited values. The final
  rule-information column still identifies explicit/inherited rules and their
  governing classification, plus instructions and remaining rule metadata.
  Metadata includes description/scope/authority/keywords, branch or terminal
  type, lifecycle information and translations.
- Code and level columns are narrow: 0.85 and 0.8 inches. Remaining column widths
  are 2.1, 0.8, 0.85, 1.65, 3.15 and 2.2 inches respectively. Their 12.4-inch total
  fits between 0.55-inch left/right margins. Set both table-grid and cell widths;
  use fixed layout and wrapping. The scheme summary uses the same usable width.
- Format timestamps for reading, using localized month names, day/year and
  24-hour hours/minutes with an explicit UTC label (for example,
  `1 January 2026, 08:00 UTC`). Omit machine timestamp syntax and fractional
  seconds from this report. Use the selected language's configured locale,
  falling back to its base language and then English if unavailable. JSON and
  CSV continue to preserve the exact source timestamps.
- Root level is 0. Use title-cell indentation to indicate increasing depth,
  an explicit level value, and different row shading by level. Include a legend.
  Never rely on color alone. At depths where distinct readable shades or
  indentation no longer fit, retain the explicit level and ancestry information;
  do not truncate or drop descendants.
- Include translations and remaining metadata within the relevant row cells
  using labeled paragraphs. Distinguish explicit and inherited retention; any
  displayed effective rule identifies its governing classification.
- Repeat column headers on subsequent pages, wrap long content, preserve
  readable contrast, and avoid clipping. Allow an exceptionally long row to
  span pages rather than losing content.
- Respect document language and RTL/LTR direction, including mixed Arabic and
  Latin codes. Do not reverse code strings. Use native Word paragraph, table,
  logical indentation and run-direction properties; do not insert Unicode
  directional control characters into document text as formatting aids.
- A scheme without classifications still exports its metadata table and an
  explicit empty-state statement.

Word is a readable report and is not an import format. Verify rendered output
for shallow, deep, broad, empty, multilingual, and long-text examples.

## 9. User interface and authorization

**IE-10:** Add an export action button to the classification-scheme details
control panel. Its menu offers JSON, CSV, and MS Word export for the displayed
scheme. Import must not appear on an existing scheme's details page.

Place a separate import action on the classification-schemes list at the same
level as the **Add Classification Scheme** button, in the same page-level
action area. It offers import from JSON or CSV using the same destination-state
and error rules. Import must be available, subject to authorization, even when
no schemes exist and without opening or selecting an existing scheme. The file
defines the new scheme to create; there is no existing target scheme selector.

Choosing MS Word exposes the supported-language selector specified in section
8 before generation; the selected language tag is passed explicitly to
the export operation rather than inferred solely from the current UI language.
Final labels are localized under the existing catalogue contract.

Show progress, prevent accidental duplicate submission while an operation is
pending, and present actionable success/error feedback. Retain the current
page and its data after failure. Download completed exports through an
authenticated flow. After a successful import, remain on the classification-
schemes list and refresh its data to reflect the committed import, preserving
the current filters, sorting, and pagination. The new scheme appears when it
matches the current list criteria and page. Show success feedback; do not
automatically open the imported scheme's details page.

No complete classification collection is downloaded to the browser to build
an export. Export traversal happens server-side from a consistent snapshot
with bounded processing. Expensive work is initiated only by the action, not
by loading the details page. Follow repeated-navigation, abandonment, freshness,
identity isolation, and RTL/LTR verification in the performance contract.

**IE-11:** Use the existing global privilege `classifications.administer` for
all import and export operations. This is the exact existing privilege code;
no new import/export privilege is introduced.

| Operation | Required privilege |
| --- | --- |
| Export JSON, CSV, or MS Word in any supported language | `classifications.administer` |
| Import JSON or CSV, including all scheme and classification translations | `classifications.administer` |

Import is one atomic operation that creates a complete new scheme, including
its translations. Neither `classification_scheme.modify_metadata` nor
`classification.modify_metadata` is additionally required, regardless of which
entities have translations. Do not strip translations based on those privileges.
This authorization applies specifically to import; existing permissions for
editing translations on existing entities remain unchanged.

Export likewise requires neither metadata-editing privilege. `audit.view` is
not required: the package contains current state and export provenance, not
source audit history. Viewing a scheme alone does not grant import or export.

Enforce `classifications.administer` server-side for every format and reflect
it in UI action availability. Reject an unauthorized operation without database
changes. The concrete routes and reuse of existing import audit vocabulary are documented in section 10.1.

## 10. Implementation constraints

- Preserve the original source lifecycle metadata as provenance, while always
  importing the scheme with a NULL destination publication date under IE-12.
  Preserve other lifecycle values as resolved under D2 without allowing ordinary
  create/update clients to forge system-managed fields. The import path must
  reconcile this requirement with timestamp, version, first-use, and event
  triggers; document how the implementation satisfies the approved D2 contract.
- Imported source actors are provenance snapshots, not authenticated destination
  identities. Never impersonate them or attach history to coincidentally equal
  destination user IDs. Local import activity is attributed to the actual
  importing user. Local import activity reuses the existing CREATE action and api/web_ui event sources, as documented in section 10.1.
- Any schema change updates the self-contained canonical schema and supplies
  a separate upgrade migration. No SQL file may contain psql meta-commands.
- Keep maintained translation catalogues aligned by contextual message key,
  preserve curated Arabic wording/provenance, and complete the required checks.
- Do not introduce a new cache without its full contract. Do not add optional
  document-generation dependencies to the initial authenticated critical path.
- Add a fully valid JSON fixture and matching complete CSV fixture as part of
  implementation; illustrative examples here are not conformance evidence.

### 10.1 Concrete implementation mapping

Implementation notes, transaction/trigger details, provenance recovery, resource
limits, deployment revision configuration, and disposable test commands are in
[`backend/services/api/scheme_transfer/README.md`](../backend/services/api/scheme_transfer/README.md).

The import endpoint is `POST /api/v1/classification-schemes/import?format=json|csv`
with one multipart `file`; success returns HTTP 201 with destination `id`, `code`,
and `date_published: null`. Export is
`GET /api/v1/classification-schemes/{scheme_id}/export?format=json|csv|docx`;
Word additionally requires `language=<enabled language tag>`. Both enforce
`classifications.administer` and retain the existing authentication/CSRF flow.

Import introduces no new audit source/action, entity, or privilege. Export
auditing is specified separately in section 10.2; verification is recorded below.
Each existing immutable CREATE history row records the source manifest and source
entity snapshot in `metadata.classification_scheme_import`; the history entity ID
and after-state ID supply the local side of the mapping. The original source
publication date is in the scheme's source snapshot. INSERT preserves supplied
lifecycle dates/versions; existing UPDATE triggers and first-use restrictions
apply thereafter. Local activity retains the actual authenticated importer.

For `source.schema_version`, applied migration versions are sorted and joined
following `migrations:`. Canonical installations with an empty migration ledger
use `canonical-sha256:` plus the SHA-256 of the bundled canonical schema file.
This identifies release provenance; it is not an assertion that an independently
modified live schema has been audited for drift.

The implementation rejects packages above 32 MiB or 10,000 classifications,
without truncation. Traversal is iterative; there is no independent hierarchy
depth limit. Deployment ingress must also bound multipart request bodies.

### 10.2 Successful export event history

**IE-14:** Every successful classification scheme export in JSON, CSV, or Word
creates one immutable event-history entry in the source database, with operation
`EXPORT` and entity type `classification_scheme`. Record the scheme ID and a
human-readable scheme code/title snapshot, occurrence time, authenticated actor
ID and name/email snapshots, the normal request source and request/correlation
context, and export metadata containing `export_id` and `format`. For Word,
also record the selected export `language`. JSON/CSV event `export_id` must
match the package manifest's `export_id`.

Success means that the server generated and validated the complete export and
committed its history entry before returning the successful download response.
It does not mean that the browser saved or opened the file. Authorization,
validation, or generation failures must not create a successful `EXPORT` event;
if history cannot be committed, do not return a successful export response.
Export leaves scheme, classification, and retention-rule rows unchanged. The
new history entry is not included in the exported package, and source history
continues to be excluded from transfer.

Recording the event does not add a privilege requirement: exporting still
requires `classifications.administer`, without `audit.view`. Viewing the entry
uses the existing authorized Audit Trail and its normal filters and redaction
rules; no separate export-history page or privilege is introduced.

## 11. Acceptance conditions and verification traceability

Every row below needs concrete implementation paths and passing verification
evidence before the feature can be declared complete. References below identify implemented coverage; section 11.4 records run results and remaining acceptance work. They do not waive any mandatory case.

| Requirement | Required verification | Implementation/evidence |
| --- | --- | --- |
| IE-01 | Snapshot consistency during concurrent edits; all classifications included despite UI filtering/pagination | `service.export_package`; `test_snapshot_and_no_source_mutation`, `test_api_hierarchy_shapes` |
| IE-02 | Cross-database export/import/export comparison of every field and remapped relationship, including lifecycle metadata, rules, and translations; account explicitly for IE-12's NULL destination publication date and verify the original publication date remains recoverable as provenance | `service.import_package`; `test_roundtrip_and_provenance`, `test_two_database_roundtrip`, `test_api_hierarchy_shapes` |
| IE-03 | Null versus empty values, absent translation keys, empty objects, Arabic, quotes, line breaks, leading zeros, microseconds, bigint IDs/versions beyond 2^53 through PostgreSQL bigint maximum | `codec.py`; `test_codec_values_and_reordering`, `test_null_empty_and_missing_translation_fields`, `test_first_use_and_publication_workflow` |
| IE-04 | Valid JSON Schema fixture; reject duplicate properties at every depth, unknown fields/versions, wrong types, missing required values, broken references | `v1.schema.json`, `codec.validate`; `test_invalid_json`, `test_integrity_edge_cases`, `test_invalid_domain_no_writes` |
| IE-05 | RFC 8785 conformance and deterministic digest; data/manifest tampering, malformed digest, duplicate checksum properties, formatting/key-order/escape equivalence, array-order changes, invalid Unicode and non-finite number rejection | `codec.digest`; `test_jcs_reference_vector`, `test_checksum_failure_no_writes`, `test_integrity_edge_cases` |
| IE-06 | Parse full CSV into the shared model and compare every field with JSON model; check row width, quoting, duplicate detection, typed values | `codec.to_csv/from_csv`; `test_checked_in_fixtures_match`, `test_codec_values_and_reordering`, `test_invalid_csv` |
| IE-07 | Successful transaction in both formats; cycles, orphan parents, terminal children, missing effective rules, invalid dates, unsupported language all rejected | `service.import_package`; `test_invalid_domain_no_writes`, `test_unsupported_language`, `test_disabled_language_is_atomic` |
| IE-08 | Second import within and across JSON/CSV, case variant, concurrent duplicate across formats, late insertion failure; verify no partial rows or modifications after failure | Unique indexes + request transaction; `test_roundtrip_and_provenance`, `test_concurrent_duplicate`, `test_case_variant_duplicate`, `test_late_failure_rolls_back` |
| IE-09 | Render English (LTR), Arabic (RTL), and an additional enabled test-language DOCX export without adding language-specific selection logic; inspect localized labels, entity fallback, paragraph/table direction, indentation from the correct edge, mixed-language codes, landscape layout, one table per root, hierarchy, colors, repeated headers, long content, and equal data coverage | `word.render_word`; `test_word_languages`, `test_api_hierarchy_shapes`; rendered review in section 11.4 |
| IE-10 | Live browser import alongside Add Classification Scheme, import available on an empty schemes list, no import on existing scheme details, JSON/CSV import choices, details-page export menu, all enabled Word language choices available independently of UI language, newly enabled language appears without code changes, disabled/unsupported selection rejected, explicit export-language selection, downloads, remain on schemes list after successful import with refreshed data and preserved filters/sort/page, failure retention, progress, repeated navigation, abandonment, freshness, LTR and RTL | `classification_transfer.py` + workspace integration; NiceGUI interaction tests and live browser checks; completed matrix evidence in section 11.4 |
| IE-11 | Anonymous/unauthorized access denied; classifications.administer permits all export formats without metadata privileges or audit.view; the same privilege alone permits complete imports including translations without metadata privileges or audit.view; test scheme-only, classification-only, both, null, and empty translations in JSON and CSV; missing privilege rejects all writes without stripping data; UI base-permission gating and identity/provenance attribution verified | Route dependencies + UI gating; `test_only_administer_privilege`, `test_anonymous_transfer_denied`, `test_transfer_hidden_without_administer` |
| IE-12 | Import draft, published, and future-publication source schemes; verify each destination scheme has NULL `date_published`, displays as unpublished/draft, is not eligible through published-scheme selectors, retains source publication provenance, and can subsequently use the existing authorized publication workflow subject to its normal eligibility rules | NULL publication override; `test_draft_import`, `test_first_use_and_publication_workflow`; live imported-draft display verified |
| IE-13 | Complete CSV reconstructs the matching JSON package and digest; real CSV export/import round trip; shuffled rows, BOM, equivalent quoting and outer line endings; null/empty translations, bigint precision; reject missing/duplicate manifest fields, checksum tampering, wrong headers/row widths/types, conflicting owners, orphan translations/rules, malformed quoting and cycles; verify draft state and rollback | Shared typed package/checksum; JSON/CSV roundtrip, parsing, rollback tests; checked-in matching fixtures |
| IE-14 | JSON, CSV, and Word successful exports each create one attributed EXPORT event with scheme snapshot, format, export ID and Word language; verify package/event ID agreement, unchanged source entities, authorized Audit Trail visibility, and no successful event/response after authorization, validation, generation, or history-commit failure | `routes.export_scheme`; `test_export_audit.py`; 2026-10-05 evidence in section 11.5 |

Database-backed verification must create uniquely named disposable PostgreSQL
databases per run, initialize empty databases from `database/schema.sql` alone,
point the complete process and fixtures only at these databases, and terminate
connections/drop them after success or failure. Cross-database tests use two
disposable databases. Report creation or cleanup failures. Never test against
a persistent development, staging, or production ERMS database.

### 11.1 Mandatory test environment

Acceptance requires successful automated database/API and browser tests against
fresh, uniquely named disposable PostgreSQL databases initialized from the
latest checked-in `database/schema.sql` alone. Cross-database tests require
separate disposable source and destination databases. Any migration-specific
verification uses an additional disposable database and the applicable migration
path; it does not replace fresh-schema acceptance coverage.

Before executing feature tests, the setup must:

1. Install and enable the supported languages and load and publish their UI
   translation catalogues through the supported language/catalogue setup
   workflow. Include English, Arabic, every other maintained supported language,
   and an additional test language to verify extensibility without hard-coded
   English/Arabic choices. Test-only catalogue content stays in disposable
   databases and must not replace checked-in curated translations.
2. Assert language registry, direction, required active-key coverage, and
   publication state, and verify published catalogue messages are served.
   Enabled language rows alone are insufficient. Entity translation objects
   remain entity metadata; do not invent a publication state for them.
3. Configure the entire test process, API servers, browser sessions, fixtures,
   background work, and export workers to use only the disposable databases.
   Fail before feature execution if database isolation or language setup cannot
   be verified. Do not fall back to a persistent database or skip failed setup.
4. Seed representative schemes, hierarchies, explicit and inherited rules,
   translations, and users with the privilege combinations required below.
   Use fresh destinations or restore isolated fixture state between cases so
   previous imports cannot mask failures or invalidate success cases.

Negative language-compatibility cases deliberately remove or disable a language
only within their isolated destination fixture after the positive baseline has
been verified. They must not alter the fixtures used for subsequent cases.

Always stop test servers/workers, close connections, and drop every created
database in finally-style teardown, including after partial setup or test
failure. Terminate remaining connections when needed. Report creation and
cleanup failures as run failures, with database names sufficient to identify
any cleanup work still required. A run with failed cleanup is not acceptance
success. No persistent ERMS database may be used.

### 11.2 Required automated acceptance cases

All groups below are mandatory. Parameterize format-neutral import cases over
both JSON and CSV, and language-dependent cases over the installed supported
languages. Record concrete test identifiers and run evidence against the
corresponding IE requirements in the table above.

| Group | Conditions for acceptance | Traceability |
| --- | --- | --- |
| AT-01: complete transfer | Export a populated source scheme and import into a fresh destination in each format. Compare every transferable field, hierarchy edge, explicit rule, and translation; verify new local IDs and retained source mappings. Re-export and compare with explicit allowances only for export provenance, remapped identities, and the required NULL destination publication date. Include empty schemes, multiple roots, deep/broad hierarchies, deactivated entities, and data exceeding one UI page. | IE-01–03, IE-06–07, IE-13 |
| AT-02: languages and exact values | Preserve English, Arabic, and additional-language entity translations; absent translated fields, null and empty objects, empty strings, quotes, embedded newlines, leading-zero codes, bigint limits, and microsecond timestamps. Verify installed published catalogue wording is used for generated labels and documented fallback rules apply. | IE-02–03, IE-09, IE-13 |
| AT-03: language compatibility | Imports with missing or disabled destination translation languages fail atomically with actionable errors. No translation is removed, no language is implicitly enabled, and no partial scheme is created. | IE-03, IE-07 |
| AT-04: unpublished destination | Import draft, published, and future-publication source schemes in each format. Verify NULL destination date_published, retained source publication provenance, draft/unpublished display, exclusion from published-scheme selectors, and subsequent use of the existing publication workflow subject to normal eligibility. | IE-12 |
| AT-05: duplicates and races | Test JSON→JSON, CSV→CSV, JSON→CSV, and CSV→JSON reimports, including case-variant codes. Competing imports on separate connections must produce exactly one committed scheme. Verify unchanged existing data and no partial entities or provenance from the rejected operation. | IE-08 |
| AT-06: rollback | Inject a controlled failure after writes begin, including a late failure after translations/rules/provenance are written. Verify rollback of all imported entities, relationships, translations, provenance, and transactional event-history rows; pre-existing destination data remains unchanged. Sequence gaps are permitted under IE-08. | IE-07–08 |
| AT-07: integrity and parsing | Reject changed content/provenance, missing or malformed checksums, duplicate JSON properties at every depth, wrong types, unknown fields/versions, and invalid Unicode/numbers. Verify JCS conformance and digest stability for permitted whitespace/key-order/escape changes; array or string content changes invalidate the digest. Negative domain tests must use valid recomputed checksums so they reach the intended validation. | IE-04–05 |
| AT-08: CSV reconstruction | Reconstruct the same typed package and digest from the complete CSV fixture. Test shuffled rows, BOM, equivalent quoting, outer record separators, and embedded text newlines. Reject duplicate/missing manifest rows, wrong headers/widths/types, malformed quoting, inconsistent owners, orphan translations/rules, missing fields, and checksum tampering. | IE-06, IE-13 |
| AT-09: domain constraints | Reject cycles, missing parents, duplicate class codes including case variants, terminal classifications with children, invalid dates, and terminals lacking effective retention. Verify explicit/inherited rule distinction and retained first-use governance. | IE-02, IE-07 |
| AT-10: authorization | classifications.administer alone permits every export and complete imports with scheme/classification translations. Test without either metadata privilege or audit.view. Anonymous users and users lacking classifications.administer are denied without writes. Metadata privileges alone do not grant import/export; ordinary translation-editing permissions remain unchanged. | IE-11 |
| AT-11: source consistency | Coordinate concurrent source edits deterministically while an export is running; verify a single coherent snapshot rather than mixed versions. Check that export does not modify source entities, and all rows are included independently of browser filters, pagination, or collapsed branches. | IE-01 |
| AT-12: provenance and history | Verify source-to-local mappings, source dates/versions/publication provenance, source exporter snapshot, and attribution of local import activity to the actual importing user. Source event history is not copied or attributed to coincidentally matching destination user IDs. | IE-02, IE-07, IE-11 |
| AT-13: Word structure | Generate Word documents in every enabled supported language and the additional test language. Assert language settings, paragraph/table direction, landscape orientation, one classification table per root, all descendants, hierarchy indentation, row shading, repeated headers, labels, and complete content. Include empty, long-text, deep, broad, and mixed-script fixtures. | IE-09 |
| AT-14: browser behavior | Verify Import beside Add Classification Scheme, including an empty list; no Import on details; JSON/CSV upload success/failure; Export formats on details; enabled-language choices independent of UI language. Success stays on the refreshed schemes list with filters, sorting, and pagination preserved. Verify duplicate-submit prevention, repeated navigation, pending-request abandonment, post-mutation freshness, user isolation, and both LTR and RTL layouts. | IE-10–11 |
| AT-15: successful export auditing | Exercise all formats and enabled Word languages; verify IE-14 attribution, metadata, one event per successful request, authorized Audit Trail retrieval, package/event export-ID agreement, unchanged source entities, and failure behavior, including a forced history-commit failure. Existing transfer evidence does not satisfy this new case. | IE-14 |

### 11.3 Acceptance evidence and visual verification

All automated groups must pass; missing, skipped, or unimplemented required
cases do not count as acceptance. Attach the test commands, schema revision,
language/catalogue setup assertions, test identifiers/results, and database
creation/cleanup results to the implementation handoff. Resolve failures before
claiming the feature complete.

Automated DOCX structure checks must be supplemented by rendering and inspecting
representative documents for clipping, page breaks, readability, hierarchy
colors/indentation, and mixed-direction content in English, Arabic, and the
additional test language. Verify browser appearance in live LTR and RTL views,
including consistency with existing Wathiq controls and tables. Record visual
verification evidence alongside automated results; neither substitutes for the
other. Required translation coverage, placeholders, terminology, stale-key,
provenance, ordering, and artifact-hash checks must also pass.

### 11.4 Implementation verification record (2026-09-29)

Verification used the working tree based on Git commit
`59997e92fbd1535f07e6ba0f2bfba5d626564a6a`, with canonical schema SHA-256
`269b1db0f85987a36c3b96633100034117767b981d9103dc2e93e2b96067ed09`.
The implementation is uncommitted; the base SHA alone does not identify these
changes.

- `backend/services/api/.venv/bin/python tools/test_scheme_transfer.py`:
  106 tests passed. The fixture asserts English source coverage and installed,
  enabled, published Arabic and French test catalogues before feature tests.
  Source `erms_transfer_test_c3012409e32649e2_source` and destination
  `erms_transfer_test_8397683940794961_destination` were both dropped after
  browser preview shutdown. No persistent application database was tested.
- After fixing per-line mixed-script isolation in RTL Word output, the same
  runner with `-k 'word_languages or api_hierarchy_shapes'` passed 15 tests
  (91 deselected). Both databases for that run were dropped successfully.
- The added `test_word_rejects_missing_unsupported_or_disabled_language`
  cases passed separately (3 passed, 106 deselected), rejecting every invalid
  selection without silently substituting a language. Both fresh databases
  were dropped successfully. The current suite contains 109 tests.
- Frontend verification: run the workspace and transfer tests under
  `frontend/webui/interaction/tests/` together with
  `frontend/webui/tests/test_api_client.py`, using the frontend virtualenv,
  pytest and `--asyncio-mode=auto`: 74 tests passed.
- Live browser checks exercised JSON import followed by CSV duplicate rejection
  and CSV import followed by JSON duplicate rejection on separate disposable
  previews. They verified draft display, list retention, filter preservation,
  refresh, details-only export, language registry choices, and successful
  authenticated JSON, CSV and Word export responses. The reusable phased checks
  are in `frontend/webui/interaction/browser/classification_transfer.js`.
- Dialog appearance and computed direction were inspected in English and
  Arabic at 1280-pixel and 390-pixel viewport widths. Both directions fit the
  viewport. A scoped correction fixes inherited double reversal in RTL fields.
- Normal and long-text Word samples were rendered and inspected in English,
  Arabic and the additional French test language. Long samples span three pages,
  preserve mixed-script text, repeat headers and continue long rows without
  clipping. Test French labels intentionally use `FR ...` markers, not a
  production French translation. Generated QA documents are disposable artifacts.
- Catalogue source coverage/stale-key checks and full Arabic quality validation
  passed. There are 53 new contextual keys, with matching maintained-language
  coverage, sorted order and updated source hash. Existing Arabic wording and
  provenance are preserved. New Arabic entries remain machine-generated drafts
  requiring human review; no administrator export was promoted or overwritten.

The follow-up acceptance run closed the previously recorded browser and visual
gaps:

- Full suite: **109 passed**, with no skipped feature tests. Source
  `erms_transfer_test_376ef3a731274762_source` and destination
  `erms_transfer_test_7f8cf2ab5cee47f4_destination` were dropped after preview.
- Live paging: seeded 60 disposable schemes, selected Creation order, loaded
  two pages, imported successfully, and asserted the same sort and 50 loaded
  rows after refresh. Existing filtered-import checks cover filter retention.
- Live timing: a separate disposable transaction held the schemes table in
  SHARE mode. A double-click disabled the import control and produced exactly
  one POST in the API log. After canceling the dialog and navigating to Dashboard,
  releasing the gate completed the import without replacing the dashboard.
  Revisiting and filtering to the imported code showed the committed draft.
- Live identity: repeated the held request with a distinct package, signed out,
  and signed in through normal controls as a separately seeded viewer with no
  roles. Releasing the gate did not expose the former user's result, notification,
  scheme navigation, or transfer controls. The viewer's account menu confirmed
  its own identity and no assigned roles.
- Truly empty destination: `--preview -k test_anonymous_transfer_denied` initializes
  published languages and accounts but creates no schemes. Import was available
  beside Add with no filter; three Dashboard/list visits followed by CSV import
  succeeded and refreshed the same list. Both preview databases were dropped.
- Empty, multiple-root, broad (80 classifications), and deep (levels 0–79)
  Word samples were rendered and reviewed in English, Arabic and the additional
  test language. Broad/deep reports span 32 LTR or 35 RTL pages. Page overviews
  and detailed edge/depth inspection verified headers, row continuation, text,
  hierarchy, and margins. This exposed an RTL indentation bug: physical `w:right`
  was rendered at the wrong edge. Logical `w:start`/`w:end` now follows document
  direction, with bounded indentation and explicit depth/parent still present.
  Final normal samples and the level-79 Arabic page were rendered again.
- After that Word fix, **15 affected tests passed** (94 deselected) on source
  `erms_transfer_test_30621ade366847fd_source` and destination
  `erms_transfer_test_40f3d44682a942ec_destination`; both were dropped.
  The frontend/client suite passed again: **74 tests**.
- Rapid sign-in navigation exposed a null-principal exception in the new privilege
  lookup. The workspace now waits for an available principal before starting
  authenticated requests; no privileges are inferred during initialization.
  Live retest confirmed the early click issued no schemes request, sign-in stayed
  authenticated, and subsequent navigation succeeded. Its source
  `erms_transfer_test_7fc71d6d04614c74_source` and destination
  `erms_transfer_test_59d41ce140764617_destination` were dropped successfully.

Browser assertions and reproduction steps are maintained alongside
`classification_transfer.js`. All timing gates were released, preview workers
stopped and test databases dropped. There is no unresolved transfer acceptance
failure. Human review of the 53 new Arabic drafts remains a translation workflow
requirement, not a claim that machine-generated wording has been approved.
All 53 entries contain best-effort Arabic text; “draft” describes review status,
not missing translations. A subsequent language pass improved 10 new entries,
including import-hint agreement, application-revision wording, retention-period
labels and consistency with the existing Authority label. Replaced machine text
is recorded in `superseded_translations`. Full catalogue validation passed again;
curated entries and their provenance remain unchanged. No administrator export
was promoted and no persistent database translations were published by this pass.

A reported bulk-publication warning subsequently confirmed that the `demo`
database still contained 53 English `source_copy` transfer drafts. An explicit
scoped seed replaced those 53 untouched rows with the validated Arabic artifact
text in one transaction. Each remains an unpublished `generated` draft with
artifact hash and machine provenance; no reviewed or published row was changed.
Read-back verification confirmed all 53 texts match and zero transfer source
copies remain. This was an operational draft update, not a test against a
persistent database or automatic publication. API startup intentionally does
not seed generated translations; artifact updates require explicit draft seeding.

The previously unclassified
`GET /api/v1/number-suggestions/{resource}` operation is now recorded as
`relationship_scoped`, reflecting its runtime selection of the applicable
creation privilege and its additional parent-visibility check when a parent
aggregation supplies the numbering context. The two transfer route entries
remain recorded with the approved existing privilege.
The no-role viewer also exposed an existing dashboard storage-chart error when
the authorized unit list is empty (`max(1, *empty)`); transfer identity isolation
remained intact. That unrelated dashboard defect is not changed here.

### 11.5. Reader-oriented Word revision verification

The September 29 Word revision implements native paragraph/table/run direction,
Changa 10 for Latin and complex scripts, 13.5 × 8.5-inch landscape pages,
friendly localized dates, compact code/level columns, and the three effective
retention columns immediately after the title. Existing translation keys are
reused; this revision adds no catalogue entries or changes to curated wording.

The focused disposable-database run passed **15 tests** (three language exports
and twelve JSON/CSV hierarchy cases). Assertions cover page geometry, font slots
and sizes, exact grid/cell widths, inherited retention values, localized dates,
native direction properties, absence of inserted direction controls, repeated
headers, hierarchy indentation and shading. Source database
`erms_transfer_test_9fbeddd097534dad_source` and destination
`erms_transfer_test_3ed435e3735745ab_destination` were both dropped successfully.

Rendered English, Arabic and French fixtures were visually reviewed, together
with English/Arabic long-text cases and 80-node deep/broad hierarchies. Tables
remain within the margins; Arabic column order, indentation, repeated headers
and level shading remain correct. The preview renderer initially substituted
DejaVu; an explicit QA font configuration resolved this, and PDF font inspection
confirmed Changa Regular/Bold. Native Microsoft Word was not used for this
rendering check. Automated DOCX assertions verify its native formatting markup.
`git diff --check` and formatting checks passed.

### 11.5 Export audit verification (2026-10-05)

IE-14 / AT-15 is implemented in `routes.export_scheme`. The complete transfer
suite passed 118 tests using two freshly created disposable databases; both were
dropped. Nine strengthened new acceptance cases passed again in two further
disposable databases, also dropped. Coverage includes JSON/CSV manifest-event
ID agreement, English/Arabic/French Word languages, actor/request/source
attribution, unchanged scheme/classification/retention-rule rows, authorized
history retrieval, validation/generation failures, and deferred history-commit
failure without a successful response or retained event. Existing privilege and
anonymous-access regressions also passed. Detailed traceability, UI evidence,
and deployment records are in
[`docs/verification/classification-export-audit/verification.md`](../docs/verification/classification-export-audit/verification.md).

## 12. Decisions and remaining clarification

| ID | Decision | Resolution/status |
| --- | --- | --- |
| D1 | Does complete transfer include immutable source event history? | Approved: transfer current entity state and provenance only; exclude source event history. |
| D2 | How should source IDs, dates, first-use markers, and versions survive import? | Approved: preserve original dates, first-use markers, and versions, except the destination scheme has NULL date_published and retains the source publication date as provenance. Allocate local IDs and persist the source-to-local provenance mapping. Imported first-use markers retain their governance effect. Document storage and trigger interaction before coding. |
| D3 | Successful-import navigation | Approved: stay on the schemes list after successful import and refresh its data. Import remains alongside Add Classification Scheme, never on an existing scheme's details page. |
| D4 | Authorization, API routes, and import audit vocabulary | Authorization approved and revised: classifications.administer alone permits the entire import, including translations, and all export formats. No additional metadata privileges are required. Concrete route mapping is documented in section 10.1. Reuse existing CREATE/api/web_ui history with import provenance metadata; no new import audit vocabulary is introduced. Export auditing is governed by IE-14. |

D1, D2, D3, import placement, and the revised privilege mapping are approved.
D5 approves successful export event history as specified by IE-14; implementation
and acceptance evidence are recorded in section 11.5.

D4 technical mapping is recorded in section 10.1. Full acceptance remains subject to every condition in section 11; implementation progress does not waive these conditions.
