# Full-text search — Phase 0 exit reconciliation

**Decision:** PASS — Phase 0 complete  
**Date:** 24 September 2026  
**Specification:** Approved revision 0.23

## 1. Exit statement

Phase 0 is complete. The initial format set, representative and hostile corpus,
quality gates, detector policy, PostgreSQL 18 behavior, OCR languages and
conservative resource defaults are approved and backed by reproducible
evidence. No Phase 1 schema or product behavior is claimed by this decision.

## 2. Phase-entry requirement inventory

The Phase 0 inventory was derived from the complete specification as required
by §1.1. Applicable requirements are:

- §1.1: create and maintain traceability, enumerate the phase, reconcile both
  directions, list unresolved work, and use/clean disposable databases;
- §2.3: confirm Tika, Tesseract, English/Arabic OCR and supported extraction
  formats while keeping preview separate;
- §2.6: approve the initial allowlist and measurable release gates;
- §7: select a pinned offline detector, confirm explicit PostgreSQL 18
  configurations and define safe mixed/unknown fallback behavior;
- §8.5: use representative corpus results to select documented starting limits;
- §15 Phase 0: assemble native, scanned, image, corrupt, protected, large and
  adversarial fixtures and confirm PostgreSQL/OCR dependencies;
- FTS-10: approve English/Arabic native and OCR quality thresholds;
- Phase 0 portions of FTS-18, FTS-52, FTS-53 and FTS-55.

The exact row-level mapping is in
`docs/full-text-search-implementation-traceability.md` §2.

## 3. Requirement-to-evidence reconciliation

| Requirement group | Evidence | Result |
| --- | --- | --- |
| Traceability and full requirement inventory | Implementation traceability §§1–3 | Satisfied |
| Every initially supported format represented | Base manifest plus `phase0-formats/` and edge manifest | Satisfied |
| Native English/Arabic/mixed documents | 1,200-document corpus and validation summary | Satisfied |
| Image-only content and scanned PDFs | PNG/JPEG base fixtures plus three scanned PDFs | Satisfied |
| Corrupt, protected, large and hostile inputs | Dedicated Phase 0 subdirectories and SHA-256 manifest | Satisfied |
| Native extraction quality | 100% English and Arabic word recall in the sampled matrix | Satisfied |
| OCR quality | English 100%; Arabic 97.34%; marker recall 97.22% | Satisfied |
| Detector and fallback decision | Lingua 2.1.1 policy; 91.53% against 90% gate | Satisfied |
| PostgreSQL 18 objects and matching | 18.6 disposable-cluster result; Arabic and English matches true | Satisfied |
| English/Arabic OCR packs | Installed inventory and 36 successful `eng+ara` cases | Satisfied |
| Benchmark-derived limits | Normative §8.5 table and benchmark report §5 | Satisfied |
| Disposable database hygiene | Unique database name; drop, stop and temp removal all true | Satisfied |

## 4. Implementation-to-requirement reconciliation

Every material Phase 0 artifact maps back to an approved requirement:

| Artifact or decision | Approved requirement |
| --- | --- |
| Edge-corpus generator and subdirectories | §§2.3, 2.6, 14 and 15; FTS-10/11/52 |
| Tika/Tesseract benchmark and thresholds | §§2.3, 2.6, 8.5 and 15; FTS-10 |
| Lingua selection and confidence/script decision layer | §7; FTS-52 |
| PostgreSQL 18 disposable verifier | §§1.1, 7 and 15; FTS-18/53 |
| Initial format allowlist | §§2.3 and 15 corpus requirement |
| Initial resource defaults | §§5, 8.4, 8.5 and 14 |
| Traceability and this exit report | §1.1 and FTS-55 |

No privilege, entity, workflow, state, endpoint, response contract or UI
behavior was added in Phase 0. DOC/XLS/PPT and ODF fixtures exercise formats
already covered by the approved Tika/office-format decision. The explicit
allowlist narrows the initially accepted parser surface.

## 5. Unresolved requirements, limitations and deferrals

There are no unresolved requirements assigned to Phase 0 and no approved Phase
0 deferrals.

The following are deliberately assigned to later phases and do not weaken this
exit:

- Phase 1 must encode the PostgreSQL configuration precondition in both the
  canonical schema and migration and prove fresh/migration parity.
- Phase 2 must implement the isolated worker process using the complete
  checksum-pinned official Tika binary distribution, pin dependencies,
  enforce every approved byte/page/time/CPU/memory/output/network limit, and
  rerun the quality gates inside that production runtime.
- Phase 2 must integrate the approved language policy and prove rebuild-version
  behavior; Phase 0 supplies the decision and corpus baseline.
- Real production throughput and capacity remain deployment-specific. Phase 0
  timings are functional reference-host evidence, not an SLA.

The Homebrew Tika 4.0.0 CLI's optional `--fork` packaging lacks a pipes-fork
class. Phase 0 therefore used an external hard timeout around ordinary CLI
invocation. This does not authorize an in-process production parser. Phase 2
must use the complete official Tika binary distribution, verify
`PipesForkParserConfig`, pass a fork-mode startup self-test, and enforce the
specified process sandbox and timeouts. Homebrew Tika and Docker are not
runtime fallbacks. The issue is recorded as an implementation constraint, not
an unexplained omission.

## 6. Phase 1 entry gate

Phase 1 may begin only from approved specification revision 0.23 and the
traceability matrix must first expand each Phase 1 section into concrete schema,
migration, authentication, metadata-search and test rows. Any product-level
departure still requires an approved specification revision.
