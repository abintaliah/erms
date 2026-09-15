# Document viewing and downloads

ERMS keeps the uploaded digital component as the authoritative original. The UI
offers two deliberately separate actions:

- **Download original** returns the stored bytes with attachment disposition.
- **View document** requests a PDF rendition and displays it with the PDF.js
  library bundled under `frontend/webui/static/pdfjs`.

Neither operation sends record content to an external service or CDN.

## Supported previews

PDF content is passed directly to PDF.js. Safe raster images use the browser's
native image renderer, while audio and video use native HTML5 media controls.
SVG is deliberately excluded because it can contain active content. LibreOffice
converts these formats to PDF on demand: DOC, DOCX, ODT, RTF, XLS, XLSX, ODS,
CSV, PPT, PPTX and ODP. Other content remains downloadable but produces an
unsupported-preview response.

Every View action opens an indeterminate **Preparing preview** progress dialog
before requesting content. For PDFs and browser-native media it explains that
the document is loading; for formats handled by LibreOffice it explains that
conversion is taking place. It remains visible until the content is received or
the API reports an error, so a large transfer or long-running conversion is not
mistaken for an unresponsive action. The indicator is intentionally
indeterminate because the current rendition endpoint does not expose transfer
or conversion percentage data.

The API searches for `soffice` or `libreoffice` on `PATH`. Set
`LIBREOFFICE_BINARY` to an absolute executable path when it is installed
elsewhere. Direct PDF viewing and all original downloads continue to work when
LibreOffice is absent.

Configuration:

- `DOCUMENT_CONVERSION_TIMEOUT_SECONDS` defaults to 60 seconds.
- `MAX_RENDITION_SIZE_BYTES` defaults to 100 MiB.
- `LIBREOFFICE_BINARY` optionally selects the executable explicitly.

For production, run conversion in a separately isolated worker or container
with CPU, memory and execution-time limits. The current synchronous conversion
is suitable for initial development but should move to a rendition job queue as
the repository grows.

## API operations

- `GET /api/v1/digital-components/{id}/content` downloads the original.
- `GET /api/v1/digital-components/{id}/rendition` returns an inline PDF.

Both require authentication. Downloads append `CONTENT_DOWNLOADED` to event
history; successful views append `CONTENT_VIEWED`. The rendition response uses
`nosniff` and a sandbox content-security policy.

## PDF.js licensing

The vendored PDF.js distribution is version 4.10.38 and is provided under the
Apache License 2.0. Its upstream license is retained at
`frontend/webui/static/pdfjs/LICENSE`.
