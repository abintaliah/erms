# Capture PDF assets

These Changa fonts are derived from the existing Wathiq web fonts in
`frontend/webui/static/fonts`. The variable WOFF2 files were converted with
fontTools 4.66.1, instantiated at `wght=400`, and saved as static TrueType fonts
(`TTFont.flavor = None`). The Arabic, Latin, and Latin Extended subsets remain
separate; the renderer uses distinct CSS family aliases so font caches cannot
confuse their overlapping internal family names. The original SIL Open Font
License is retained in `OFL.txt`.

These are offline build artifacts. Rendering does not download or transform fonts.
WeasyPrint subsets and embeds the glyphs used by each PDF. Independent acceptance
checks verify embedding, subset flags, Unicode extraction, PDF/A-2u and PDF/UA-1.

`pdfua-extension.xml` declares the PDF/UA identification namespace in PDF/A's
extension metadata. The renderer adds the PDF/UA identification to the existing
PDF/A XMP metadata without discarding its RDF structure. A declaration alone is
not treated as conformance: both veraPDF profiles must pass before commit.

The pinned renderer also needs a narrow structure-tree correction for list items
containing paragraphs or nested lists: WeasyPrint 68.1 places those block tags
directly under `LI`, whereas PDF/UA-1 requires `Lbl`/`LBody` children. The PDF
finisher reparents the existing block tags into `LBody`, preserving marked content,
parent pointers, and reading order. Nested English/Arabic lists and real amendment
histories are independently validated to cover this renderer-specific correction.
