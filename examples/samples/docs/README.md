# Bilingual full-text-search sample corpus

This directory contains 1,200 deterministic synthetic documents for Wathiq
seeding, extraction, OCR, language-detection, indexing, and search tests. No
file contains personal, confidential, or production data.

Each document contains exactly 200 body words, excluding its title and
synthetic reference. Every format includes English-dominant, Arabic-dominant,
and mixed-language samples. Topics cover finance, human resources, general
administration, asset management, records management, project management,
information technology, and procurement. The format inventory is:

- 143 each of DOCX, XLSX, TXT, PDF, PNG, and JPEG;
- 142 HTML documents; and
- 40 each of EML, Outlook MSG, XML, PPTX, and Markdown.

PPTX samples contain four slides with 50 body words per slide. EML files are
standards-compliant MIME messages. MSG files are genuine Microsoft Compound
File Binary messages containing MAPI properties. PNG and JPEG files represent
scanned pages and intentionally contain no embedded text layer.

`manifest.csv` is the authoritative inventory. It records the expected topic,
language mode, body word count, two uncommon terms, a unique search marker,
file size, and SHA-256 checksum. Image and MSG expected-body assertions use
their manifest terms because those formats do not expose body text through the
same standard-library extraction path as the other fixtures.

## Regeneration

The generator is deterministic. Run it from the repository root with the
bundled workspace Python, LibreOffice, Poppler, Node.js, and artifact-tool
dependencies. `generate_corpus.py` creates all non-XLSX files and the XLSX
payload. `generate_xlsx.mjs` creates the workbooks. `finalize_manifest.py`
calculates final hashes and validates the corpus. The extension generator uses
the pure-Python `msgforge` package to construct MSG compound files, and the
PPTX generator uses the bundled artifact-tool presentation runtime.

Generated QA intermediates use dot-prefixed names and are not part of the
1,200-file manifest. They may be removed after visual review.

## Phase 0 edge and robustness corpus

`generate_phase0_edge_corpus.py` creates the supplementary fixtures required
by the approved full-text-search Phase 0 gate. They are deliberately separated
from the 1,200-document quality corpus:

- `phase0-formats/`: DOC, XLS, PPT, ODT, ODS, ODP, RTF, CSV and TIFF coverage;
- `phase0-scanned-pdf/`: English, Arabic and mixed image-only PDFs;
- `phase0-corrupt/`: truncated or invalid PDF, DOCX, XLSX and PNG inputs;
- `phase0-protected/`: an AES-256 password-protected PDF;
- `phase0-oversized/`: a deterministic 52 MiB file above the approved 50 MiB limit;
- `phase0-adversarial/`: external-entity XML, active/external HTML, high-compression
  and nested archives, and pathological whitespace; and
- `phase0-language-edge/`: short, numeric, code-like, balanced mixed,
  unsupported-script and symbols-only inputs.

`phase0-edge-manifest.json` records the exact byte size and SHA-256 digest of
every supplementary fixture. Regenerate them with the bundled workspace Python
and the LibreOffice binary configured in `.env`. Install the pinned benchmark
dependencies from `requirements-phase0.txt` in an isolated environment first:

```bash
<workspace-python> -m pip install -r examples/samples/docs/requirements-phase0.txt
<workspace-python> examples/samples/docs/generate_phase0_edge_corpus.py
```

`benchmark_phase0.py` records machine-readable extraction, OCR, language-policy
and robustness results in `phase0-benchmark-results.json`.
`verify_phase0_postgresql18.py` creates an isolated PostgreSQL 18 cluster and a
uniquely named disposable database, verifies the required text-search catalogue
objects and matching behavior, drops the database, stops the server, and removes
the temporary cluster.
