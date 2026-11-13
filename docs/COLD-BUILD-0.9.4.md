# Cold index build — measured release 0.9.4

Date: 15 September 2026. CPU only, local files and installed dependencies; no model download or cloud service.

## Packaged UI measurements — 145 scenes / 26.75 MiB only

Hardware: Intel Core i5-8365U @ 1.60 GHz, 8 logical CPUs; 15.81 GiB usable RAM (16 GB installed).
Archive: 145 scenes, 28,044,054 source bytes (26.75 MiB). Every run used a fresh semantic cache and a SQLite backup of the same library. The live archive/cache was not cleared.

| Run | Archive | Old installed package | Installed 0.9.4 | Reduction |
|---|---|---:|---:|---:|
| First measured UI run | 145 scenes / 26.75 MiB | 88.31 s | 39.68 s | 55.1% |
| Repeat, fresh semantic cache | 145 scenes / 26.75 MiB | 45.44 s | 23.61 s | 48.0% |

These percentages apply only to the **145-scene / 26.75 MiB archive**. They are not a measured speedup for the larger `imagery_archive` (reported as 713 MB). Most savings are fixed model-startup overhead, so the percentage benefit falls as image/tile processing time grows. For illustration only, saving 23 seconds in a 280-second build would save about 8%; neither that 280-second baseline nor a new 713 MB cold-build timing was measured in this audit. Cross-run stage differences are not a guaranteed fixed saving.

These are actual WebView2 button-to-READY measurements, using the rendered BUILD LOCAL INDEX button and the packaged HTTP endpoints. The benchmark opens an isolated test window/server with shipped app files; it does not bypass the UI build handler. It does not certify the desktop launcher's single-instance or installer-on-clean-machine acceptance tests.

Windows file caching affects the repeat runs. These are cold *application-cache* builds, not rebooted/OS-cache-flushed trials. Do not mix the fastest repeat with the first old run to claim a larger gain. This is one laptop and one archive, not a statistically representative performance guarantee.

## Where time was saved

Initial installed-interpreter baseline: 66.85 s total; model loading 38.44 s, same-place verification 6.83 s, tile encoding 4.01 s. Repeated baseline: 70.71 s (background load varied).

Startup profiling identified PyTorch import (~14.8 s), OpenCLIP import (~23.8 s), model construction (~4.3 s), and checkpoint load (~1.1 s). Repeatedly importing training/model-construction libraries dominated this small archive.

The build script now prepares a TorchScript FP32 copy of the **existing local checkpoint**, plus its fixed screening prompt vectors. Runtime loads that copy directly. The exact RGB evaluation transform uses PIL/NumPy/PyTorch without importing OpenCLIP or torchvision during index startup. No thresholds, model precision, images, tiles, candidates or geometric verification steps were removed.

New first packaged run stage timings:

| Stage | Seconds |
|---|---:|
| Model startup | 15.096 |
| Screening and scene embeddings | 14.544 |
| Same-place verification | 6.187 |
| Temporal grouping and tiles | 3.506 |

The old UI's first transition out of model loading was around 66 s (sampled, not an instrumented stage timer). Most savings are startup; verification and encoding are not claimed to be drastically faster.

An intermediate approach retaining torchvision took 61.12 s in the isolated engine benchmark. Removing that import reduced a subsequent run to 45.98 s. Full runtime hashing of both 600 MB checkpoint files was also tried; that run took 56.60 s and was not retained. The final loader checks bundle version/size/timestamps, while the exporter records SHA-256 checksums. Those metadata checks are cache-coherence checks, not a tamper-proof security guarantee.

## Output equivalence

Both packaged UI runs and their repeats preserve:

- 11 temporal groups; 2 similar-site groups; 1 unmatched observation.
- 55 accepted representatives, 32 excluded records, 58 duplicate copies.
- 55 scene vectors and 28 tile vectors, byte-for-byte equal.
- Feature screening scores, review reasons, tile positions/water fractions, group membership and evidence, and unmatched IDs.

Comparison ignores only model file timestamp labels, which differ between source and installed files; it compares actual vector bytes and decisions. Equality applies to this measured archive and does not establish independent geospatial accuracy.

Exporter also checks exact preprocessing and eager/scripted image outputs on square and non-square inputs. Test suite: **123 passed**. JavaScript syntax and git whitespace checks pass.

## Progress and trade-offs

Model preparation now shows an animated, indeterminate bar and its current operation, rather than an overall 0%. Verification and tile encoding show their stage rather than pretending the build is complete at 100%. Image counts remain screening counts. Unmeasured generic minute estimates were removed; stage timing is recorded in the final status.

Accuracy trade-off observed: **none on the tested archive**. No reduced precision, GPU, cloud, or new runtime dependency.

Storage trade-off: an additional 605,310,183-byte (~577 MiB) derived model. Installer grew from about 1,025 MiB to 1,560 MiB. The original checkpoint stays available. First arbitrary text search can still load the OpenCLIP tokenizer stack; this change targets cold index creation, not every application operation. The TorchScript artifact is tied to the packaged PyTorch version; exporter validation must run for each release.

100,000 scenes have **not** been benchmarked. This improvement removes fixed startup overhead; it does not eliminate per-image encoding or structural matching costs. Larger imagery can produce far more tiles than this archive. No lakh-image throughput claim follows from these results.

## Reproduction and evidence

- `scripts/measure_packaged_ui.py`: separate native window, fresh SQLite backup, real button and status polling.
- `scripts/measure_cold_build.py`: isolated engine timings using installed interpreter.
- `scripts/compare_cold_build.py`: exact decisions, groups and vector comparisons.
- Raw local evidence: `cold-bench/ui-baseline-2`, `cold-bench/ui-optimized`, `cold-bench/ui-baseline-repeat`, `cold-bench/ui-optimized-repeat`.
- Comparison summaries: `benchmark-output/cold-ui-comparison.json` and `benchmark-output/cold-ui-repeat-comparison.json`.
- Installer: `C:\Users\abcom\Desktop\anveshan-dist\ANVESHAN-Setup-0.9.4-x64.exe`.
- Isolated installation: `benchmark-output/package-0.9.4`; successful installation log: `benchmark-output/install-0.9.4.log`.
