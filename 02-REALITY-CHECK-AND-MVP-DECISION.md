# ANVESHAN — Reality Check & MVP Decision

**10 September 2026 | Independent source inspection + fresh local experiments**

## Decision in one minute

**Public imagery aur existing software se ek useful prototype banana feasible hai. Current implementation ko trustworthy change-analysis solution bolne ka evidence nahi mila.** Existing search/index/ingestion infrastructure reuse karo; change acceptance, quality handling aur onset logic ko measured evidence ke saath improve karo.

Sabse clear failure: calibrated RemoteCLIP change baseline ne test subset par **28 true positives ke saath 116 false alarms** diye. Sirf brightness badalne par bhi onset module ne “supporting change” date return ki. Yeh PS ki meaningful-change aur false-alarm requirements ko directly affect karta hai.

Yeh universal model verdict, full-project certification ya organiser score nahi hai. Results neeche ke limited protocol par apply hote hain.

## 1. Kya inspect aur run hua

`earlier project notes` mein planning/research files mile. Referenced working application **`C:/Users/abcom/Downloads/anveshan`** mein mili. Purane audit aur comments ko claims maana; current functions aur fresh outputs se findings banayi.

Original application ko edit nahi kiya. Database/index mutations aur audit decisions workspace ki scratch copies par hue. Local checkpoint directly load hua; experiment processes mein Python socket connections blocked aur Hugging Face offline mode enabled tha. **Yeh OS-wide network-disabled browser demo ka substitute nahi hai.**

| Available asset | Verified local inventory | Implication |
|---|---|---|
| Shared FAISS + SQLite | 16,354 vectors; 16,354 rows; contiguous IDs | Basic index/metadata counts consistent |
| EuroSAT | 16,200 chips; no scene IDs or dates in stored metadata | Benchmark archive, geographic temporal evidence nahi |
| Noida Sentinel-2 search | 56 tiles; acquisition date 2026-07-12; scene IDs present | Small real geographic retrieval experiment possible |
| Noida timeline | 336 tiles; six dates, 2023-04-04 through 2026-07-12 | Real multi-date visual inspection possible; timeline sidecar drops scene IDs |
| Noida change pair | 56 complete tile pairs; 2023-04-04 vs 2026-05-03 | Real scene comparison; no ground-truth labels |
| Bhuvan captures | 98 chips; seven date labels; screenshot-based source | Labels include `2016-2012`, `2019-18,2017`, `2024-22`; not exact acquisition dates |
| OSCD RGB mirror | 14 train + 10 test pairs, binary masks | Labelled change/no-change baseline available; mirror lacks per-pair city/date/georeferencing |
| Models | RemoteCLIP ViT-B/32 checkpoint and ChangeFormer files | RemoteCLIP executed; ChangeFormer not evaluated in this experiment |

Noida chips re-embedded against stored vectors: minimum cosine **0.9999997**. This checks these 56 vector-to-image matches; full archive mapping was not exhaustively validated.

[Machine-readable inventory](reality_check/inventory.json)

## 2. Six official capabilities: quick audit

“Partial” means meaningful implementation exists, but complete official capability is not established.

| Capability | Status | Fresh evidence and remaining gap |
|---|---|---|
| Semantic + image retrieval with filters | **Partial** | Both modes executed; date filter excluded/returned correct dated subset. Text relevance weak on small fresh visual check. `area` filters source names, not arbitrary spatial AOI geometry. |
| Multi-temporal change + type + earliest evidence | **Partial; reliability failure** | Real pairs and six-date series exist. Change precision poor at tested operating point; brightness-only change yields onset date. Type logic uses before/after surface-state transitions but has no validated per-class accuracy here. |
| False-alarm suppression / quality | **Partial** | SCL and RGB heuristics exist. Applying rejection heuristics experimentally reduces false positives but precision remains 25.3%. Onset considers cloud brightness, not all confounders. |
| Discovery and clustering | **Partial** | Image similarity executes. Default HDBSCAN on 56 Noida embeddings assigns **all 56 to noise**, producing no clusters on this AOI. Similarity fallback is useful, but clustering success is not proven. |
| Analyst review and provenance | **Partial** | Scratch decision persisted and hash chain verified. GeoJSON contains tile ID, score, class, date, sensor and decision, but omits source scene and processing history. Before/after/timeline modules exist; full browser workflow not exercised. |
| Scale, incremental ingestion, offline | **Partial** | Local model/search/change ran without Python network connections. Local GeoTIFF ingestion appended two searchable tiles while preserving all 16,354 earlier vectors. Large-area scale, crash recovery and complete offline UI remain unverified. |

Relevant source: [search/filtering](C:/Users/abcom/Downloads/anveshan/src/anveshan/search.py:161), [onset](C:/Users/abcom/Downloads/anveshan/src/anveshan/onset.py:82), [rejection](C:/Users/abcom/Downloads/anveshan/src/anveshan/rejection.py:206), [clusters](C:/Users/abcom/Downloads/anveshan/src/anveshan/clusters.py), [export](C:/Users/abcom/Downloads/anveshan/src/anveshan/geoexport.py:11), [local ingestion](C:/Users/abcom/Downloads/anveshan/scripts/11_stage_local_geotiff.py).

## 3. Experiment A — real local semantic search

All 56 Noida chips were visually reviewed before rankings. Three queries and conservative relevance lists were frozen for this run. These are **provisional single-AI-reviewer judgments**, not independent human ground truth. Borderline chips treated as irrelevant can depress precision; a second reviewer is needed before using these scores in a pitch.

| Query | Relevant in top 5 | Important context |
|---|---:|---|
| closely packed residential buildings | 2/5 | Mixed built-up areas sometimes ranked over denser residential chips |
| agricultural fields and open farmland | 0/5 | Returned chips are visibly built-up; clear failure in this archive/query |
| a very large bright roof on an industrial building | 2/5 | Only 3 chips were labelled relevant, so maximum possible is 3/5 |

Warm query times were approximately **180–298 ms** on CPU. Three probes are insufficient for a general latency or relevance guarantee.

Image queries excluding the exact query chip returned **4/5, 3/5 and 1/5** relevant results for residential, farmland and roof examples respectively. Image similarity is worth keeping, with variable performance across concepts.

**Decision:** Retain RemoteCLIP as a baseline, not a final model selection. Evaluate imagery preprocessing, context/tile scale and prompt sensitivity on a separate development set. Re-evaluate changes with new, independently judged queries rather than tuning to these three examples.

[All 56 inspected chips](reality_check/noida-contact-sheet.jpg) · [Frozen judgments](reality_check/fresh_query_judgments.json)

## 4. Experiment B — actual change and labelled no-change

Protocol fixed before scoring: first three train pairs for calibration, first three test pairs for evaluation; all complete 64×64 tiles. A tile is positive if more than 2% of its benchmark mask is changed. Calibration has **244 tiles / 53 positives**; evaluation has **169 tiles / 31 positives / 138 negatives**.

Each method's threshold was selected on calibration data for at least 80% recall, then frozen on test data. That operating point is an experiment choice inherited from the baseline, **not an official target or precision-first production decision**. These public pairs were already available to the project; they are not pristine held-out or organiser data.

| Method on test subset | Average precision¹ | Precision | Recall | True positives | False positives |
|---|---:|---:|---:|---:|---:|
| Pixel difference | 0.150 | 18.1% | 90.3% | 28 | 127 |
| RemoteCLIP cosine distance | 0.198 | 19.4% | 90.3% | 28 | 116 |
| RemoteCLIP + existing heuristic rejection gate² | — | 25.3% | 80.6% | 25 | 74 |

¹ Average precision from sklearn, not trapezoidal PR area. The existing function calls this `pr_auc`; this report names the actual metric. ² Gate is an experimental composition, not a claim that the current API already suppresses detections this way.

RemoteCLIP beats pixel average precision on two of three test pairs, but loses on all three calibration pairs. This mixed result supports a measured comparison, not a blanket superiority claim. Even the heuristic variant produces about three false positives per true positive.

OSCD labels focus on **urban change**. A mask-negative field can still have crop/seasonal visual change; negatives are no labelled target change, not identical pixels. This is useful for assessing confounders. Dataset scope verified against the [authors' OSCD page](https://rcdaudt.github.io/oscd/).

On the unlabelled real Noida pair, **35/56** tiles exceeded the transferred RemoteCLIP threshold. This is a candidate count, **not 35 verified changes**.

[Per-tile raw scores](reality_check/change_tile_scores.csv) · [Real positive and negative examples](reality_check/real-change-and-negative-examples.jpg)

## 5. Confounders expose the earliest-evidence problem

A real farmland chip was kept geometrically unchanged and modified with controlled perturbations. These are **synthetic controls on real pixels**, not real cloud/season acquisition pairs.

| Control | Existing onset output | Interpretation |
|---|---|---|
| Identical image | No date | Correct on this chip |
| Brightness ×1.15 | Returns later date as support | False support despite no structural change |
| Synthetic haze | Returns later date as support | Haze heuristic recognises it elsewhere, but onset still accepts it |
| Opaque synthetic cloud | Skips observation; no date | Correct on this control |
| Seasonal colour proxy | Returns later date as support | Colour change alone creates temporal evidence |
| Two-pixel shift | Returns later date as support | Registration difference creates temporal evidence |

Root cause: onset takes half of the maximum embedding distance within the series. A nonzero difference therefore creates its own relative threshold without first establishing meaningful target change. [Source](C:/Users/abcom/Downloads/anveshan/src/anveshan/onset.py:128)

Separate code-path check: Noida change candidate selection uses the 75th percentile and `>=`. For 56 zero scores, **56/56 become candidates**. This is candidate-selection failure, not proof that final classification labels all 56 as construction. [Source](C:/Users/abcom/Downloads/anveshan/src/anveshan/api.py:607)

Real six-date imagery also shows pronounced field-colour and brightness variation, with a broadly stable residential layout at position 13. These are visually assessed cases; exact change-free status is not independently labelled. No independently labelled **real cloud-obscured** negative set was available in this experiment, so synthetic-cloud success does not validate real-cloud robustness.

[Six-date evidence sheet](reality_check/six-date-local-evidence.jpg)

Fresh real-timeline outputs: position **13** (stable-looking residential layout) receives onset **2026-07-12**; position **40** (seasonally varying fields) receives **2023-12-10**. These dates do not establish a target structural change. At position **36**, the bright-roof chip dated 2026-07-12 is rejected by the brightness-based cloud gate (score 0.2598). Visual evidence suggests a bright roof rather than an opaque cloud; this illustrates why RGB brightness alone needs independent quality validation.

### Incremental ingestion result

The existing local GeoTIFF ingestion script was executed against scratch copies of the real index and DB, using a **synthetic two-tile georeferenced raster fixture**. Index and metadata grew **16,354 → 16,356**; both new tiles were searchable with the specified date; all old vectors were bit-identical; new pixel data round-tripped correctly. This validates the normal append path and format handling, not actual satellite accuracy or crash recovery. No Python network connection attempts were recorded.

[Workflow results, including all dated observations](reality_check/workflow_results.json)

## 6. What to reuse, change and defer

**Reuse:** FAISS/SQLite foundation, existing model-loading interface, tile/image retrieval, local raster adapter, audit persistence, before/after review scaffolding and similarity fallback. The [official RemoteCLIP repository](https://github.com/ChenDelong1999/RemoteCLIP) supports its use as a retrieval/zero-shot baseline; a change detector still needs its own validation.

**Change first:** Meaningful-change acceptance before onset; both-date quality masks and alignment checks; actual geographic AOI/date filtering; durable source IDs, footprints/transforms and processing records in exports. Remove dependence on ranked percentiles as proof of change.

**Defer from first demo:** Phone-photo geolocation/OCR, expanding a named-college screenshot catalogue, and additional presentation polish. These do not resolve the measured retrieval/change weaknesses. Date-range screenshots may remain illustrative references but should not underpin exact-date claims.

Source review also finds full-raster reads during local ingest, and separate index/image/DB writes without a shared recovery transaction. These are scale/recovery risks inferred from code, not reproduced crash failures. [Raster read](C:/Users/abcom/Downloads/anveshan/src/anveshan/local_ingest.py:37) · [Write sequence](C:/Users/abcom/Downloads/anveshan/scripts/11_stage_local_geotiff.py:62)

## 7. First MVP scope decision

**Proceed with an analyst-assisted discovery-and-review MVP. Automatic reliable change classification is not yet validated.**

Use one small configurable area with licensed georeferenced optical imagery and several usable dates. Keep text and image search, working metadata/spatial filters, similar-site discovery, before/after review, confirm/reject and provenance-rich export. Start change development with urban built-up/construction candidates, because labelled urban-change evidence is available; **this is the first class to validate, not a claim that construction is already reliable**. Water, roads, clearance and small vehicles remain unvalidated until suitable imagery and class-specific labels exist.

Before calling that demo ready:

1. Assemble independently reviewed change, no-change, seasonal, real-cloud and alignment cases. Preserve source scenes and acquisition dates; separate development/calibration/evaluation cases geographically and temporally where possible.
2. Compare a change-specific model and a normalized pixel baseline against this RemoteCLIP baseline under the same label/task definition. Cached ChangeFormer is a candidate to assess, not an automatic winner; training-domain fit and provenance still need checking.
3. Select a precision-focused acceptance threshold on development data and report held-out precision **and recall/sample count**. Explicit abstention is allowed; do not manufacture a fixed proportion of changed tiles.
4. Estimate onset only after a supported target transition passes quality checks. Report last usable no-change observation and first usable supporting observation, including unusable-date gaps.
5. Export complete evidence, add a new scene without rebuilding, reopen review decisions, and rehearse the whole UI with host network disabled.

No arbitrary deadline, numerical success threshold or full-area build-time claim is invented here. The next implementation priority is **quality-aware change acceptance + defensible onset**, accompanied by an independent local evaluation set.

## 8. Reproduce and inspect

[Full results](reality_check/results.json) · [Baseline script](reality_check/run_baseline.py) · [Workflow checks](reality_check/check_workflows.py)

Run from PowerShell using the staged Python:

```powershell
& 'C:\Users\abcom\Downloads\anveshan\.venv\Scripts\python.exe' -B '<repo>\reality_check\run_baseline.py'
& 'C:\Users\abcom\Downloads\anveshan\.venv\Scripts\python.exe' -B '<repo>\reality_check\check_workflows.py'
```

Machine: Windows 11, 8 logical CPUs, PyTorch 2.14.0+cpu, 4 inference threads, no CUDA. Baseline workload elapsed **164.6 seconds after imports**, including **22.1 seconds model loading**; startup/import overhead is excluded. Stored shared index is about 37.9 MB; checkpoint about 605.2 MB. Full original build time and peak RAM were not measured.

This report does not assess whether existing screenshots/datasets have a fully packaged licence record; that remains a submission requirement.
