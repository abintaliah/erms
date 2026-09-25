# Full-text search Phase 2 production-path benchmark

Date: 2026-09-24. The machine-readable evidence is
`examples/samples/docs/phase2-worker-benchmark-results.json`; the repeatable
harness is `benchmark_phase2_worker.py` in the same directory.

The run used the official Apache Tika 4.0.0 app binary distribution. Its
published SHA-512 was verified as
`59970cecd51dbd22f51eec1f14bfdefdf660dd9cd6f726dd7ec5dfafcd089d80927d6034c7514f8d87571a05715126e984e5e07dbf6d9033d54075a19884b92a`.
The extracted adjacent library set contains
`tika-pipes-fork-parser-4.0.0.jar`. Native documents ran through Tika's
`--fork` path with a 120-second task timeout, 768-MiB fork heap, maximum 1,000
PDF pages, and embedded depth zero. Images ran through the production worker's
separate bounded Tesseract process with the explicit `eng+ara` language set.

| Measure | Result | Gate | Outcome |
| --- | ---: | ---: | --- |
| Cases | 18 | representative native/image/scanned-PDF English, Arabic, mixed | pass |
| Unique marker recall | 100% | 100% | pass |
| English word recall | 99.69% | at least 90% | pass |
| Arabic word recall | 97.74% | at least 75% | pass |
| Median wall time | 8.480 s | under 120 s | pass |
| Maximum wall time | 11.706 s | under 120 s | pass |

An earlier diagnostic run revealed that Tika 4.0.0's CLI `--fork` path did not
carry the configured `eng+ara` Tesseract parser setting into the forked JVM on
this machine, although the non-fork path did. The worker therefore does not
depend on that behavior: image OCR is an explicitly bounded Tesseract child
process, while Tika's complete Pipes fork distribution handles the remaining
document formats. This preserves Arabic quality and crash isolation without a
Docker/Tika service or the incomplete Homebrew CLI package.

The local host cannot prove the intended Linux extractor egress policy while retaining Tika's
random loopback Pipes socket: macOS `sandbox-exec` identifies the fork IPC as
outbound networking and cannot distinguish its dynamically selected local
endpoint with the attempted static profile. Production deployment therefore
must enforce egress policy at the service/workload boundary as documented in
`docs/deployment.md`. That deployment-specific negative test remains required
at deployment. This is a deployment-environment validation gate, not unfinished
repository implementation.
