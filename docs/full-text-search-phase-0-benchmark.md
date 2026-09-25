# Full-text search — Phase 0 corpus and benchmark report

**Status:** Passed  
**Run date:** 24 September 2026  
**Specification:** `specs/full-text-search.md`, revision 0.23

## 1. Purpose and method

This report records the Phase 0 evidence used to approve the initial extraction
formats, quality gates, language policy and conservative operating limits. The
fixtures are deterministic synthetic data and contain no production or personal
information.

The base corpus contains 1,200 documents with 200 ground-truth body words per
document across English-dominant, Arabic-dominant and mixed-language content.
The supplementary corpus adds 30 format, scanned-PDF, corrupt, protected,
oversized, hostile and language-edge fixtures. Exact paths, sizes and SHA-256
digests are in `examples/samples/docs/manifest.csv` and
`examples/samples/docs/phase0-edge-manifest.json`.

Word recall is multiset overlap between normalized ground-truth and extracted
Latin- or Arabic-script tokens. It intentionally ignores punctuation-only and
whitespace-only differences. Unique-marker recall checks retrieval of a
fixture-specific token. Timing is wall time on the reference development host
and includes command/JVM startup, so it is a conservative functional baseline,
not a production throughput claim.

## 2. Reference toolchain

| Component | Verified version / decision |
| --- | --- |
| Apache Tika | 4.0.0 |
| Tesseract | 5.5.1 |
| OCR languages | `eng` and `ara` installed and exercised |
| LibreOffice | 26.8.0.3 at `/Applications/LibreOffice.app/Contents/MacOS/soffice` |
| Language detector | `lingua-language-detector` 2.1.1, local English/Arabic models only |
| PostgreSQL | 18.6, isolated disposable cluster/database |

The implementation remains required to pin and scan the complete official Tika
binary distribution and repeat these gates under the deployed process sandbox.
The Homebrew Tika CLI is benchmark tooling only and is not an accepted Phase 2
runtime dependency. Docker is not part of the approved runtime design.

## 3. Results

### 3.1 Native extraction

Thirty DOCX, XLSX, TXT, PDF, HTML, EML, MSG, XML, PPTX and Markdown cases were
sampled across all three language modes.

| Measurement | Result | Gate | Outcome |
| --- | ---: | ---: | --- |
| Successful parses | 30/30 | No systemic supported-format failure | Pass |
| English word recall | 100.00% | 98% | Pass |
| Arabic word recall | 100.00% | 95% | Pass |
| Unique-marker recall | 100.00% | 95% | Pass |
| Median wall time | 2.934 s | Informational | — |
| Maximum wall time | 3.172 s | Informational | — |

Nine supplementary DOC, XLS, PPT, ODT, ODS, ODP, RTF, CSV and TIFF fixtures
all parsed successfully and achieved 100% marker recall. This closes the
initial-format allowlist inventory without treating archives as indexable
documents.

### 3.2 OCR

Thirty-six 300-DPI-equivalent PNG/JPEG fixtures were processed with
`eng+ara`. The PNG/JPEG sources intentionally contain no embedded text layer;
the image-only PDF fixtures reuse the same controlled raster sources.

| Measurement | Result | Gate | Outcome |
| --- | ---: | ---: | --- |
| Successful OCR cases | 36/36 | 100% bounded completion | Pass |
| English word recall | 100.00% | 90% | Pass |
| Arabic word recall | 97.34% | 75% | Pass |
| Unique-marker recall | 97.22% | 95% | Pass |
| Median wall time | 1.349 s | Informational | — |
| Maximum wall time | 1.586 s | Informational | — |

The 90% English and 75% Arabic OCR thresholds are release floors, not targets.
A result below either floor blocks rollout even when combined recall would pass.

### 3.3 Language policy

Lingua was evaluated through the complete server-side decision policy, not by
treating its top label as authoritative. The policy requires sufficient text,
supported-script coverage, confidence and a dominant script. Short, numeric,
code-like, balanced mixed and unsupported-script inputs use `simple`.

The 307-case corpus produced 91.53% correct policy decisions against a 90%
gate. Incorrect dominant/mixed boundary cases fail safe to `simple`; they do
not select an unapproved dictionary. The mixed boundary is therefore an
`index_config_version` input and must be recalibrated when the corpus or
detector changes.

### 3.4 Robustness and limits

Four corrupt formats and one AES-256 password-protected PDF terminated within
the 15-second harness bound, returned no extracted output, and produced no
published content. Host-side preflight shall reject the deterministic 52 MiB
fixture against the approved 50 MiB input ceiling before invoking Tika.

A direct functional extraction of the 52 MiB repeated-text fixture completed
in 3.10 seconds on the reference host, demonstrating that the selected limit is
a risk/operability boundary rather than a parser-crash threshold. The approved
120-second extraction timeout leaves substantial margin over the representative
small-document timings while remaining bounded for hostile inputs.

Adversarial fixtures cover external-entity XML, script/external-resource HTML,
high-compression content, eight archive nesting levels and pathological
whitespace. Phase 2 must verify the production process sandbox, no-network policy,
archive/embedded-object disablement and every configured resource cutoff; Phase
0 approves the fixtures, threat cases and starting values rather than claiming
that an as-yet-unimplemented worker enforces them.

## 4. PostgreSQL 18 confirmation

`verify_phase0_postgresql18.py` initialized an isolated PostgreSQL 18.6 cluster,
created database `erms_fts_phase0_bd90412e93e4`, and verified:

- `pg_catalog.simple`, `pg_catalog.english` and `pg_catalog.arabic` resolve;
- the built-in Arabic configuration uses `arabic_stem` plus `simple` mappings;
- representative Arabic document/query construction matches under the same
  explicit `pg_catalog.arabic` configuration;
- representative English stemming/matching succeeds; and
- the disposable database was dropped, the server stopped and the temporary
  cluster removed successfully.

The original specification example used nonexistent PostgreSQL function
`to_regconfig(text)`. Revision 0.22 corrects the precondition to inspect
`pg_catalog.pg_ts_config`; application vector/query calls continue to use
schema-qualified `regconfig` names explicitly.

## 5. Approved initial limits

The initial limits are 50 MiB input, 5,000,000 extracted characters, 1,000
pages, 16,000-character target chunks with a 20,000-character hard maximum,
120 seconds, 2 CPU, 1 GiB memory and 1 GiB private temporary storage per active
job. Archive recursion and embedded-object extraction are disabled. OCR starts
with English and Arabic. Transient work receives at most three automatic
attempts. The complete configuration table is normative in specification
section 8.5.

These values are deliberately conservative. Raising one requires a repeatable
benchmark in the intended deployment image and an operations-document update.

## 6. Reproduction artifacts

- `examples/samples/docs/generate_phase0_edge_corpus.py`
- `examples/samples/docs/benchmark_phase0.py`
- `examples/samples/docs/verify_phase0_postgresql18.py`
- `examples/samples/docs/phase0-benchmark-results.json`
- `examples/samples/docs/phase0-postgresql18-results.json`
- `examples/samples/docs/phase0-edge-manifest.json`

Machine-readable results are authoritative for individual cases. This report
records the reviewed gates and interpretation.
