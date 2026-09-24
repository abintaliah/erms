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
1,000-file manifest. They may be removed after visual review.
