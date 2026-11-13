# ANVESHAN — architecture note

PS 2.3 requires an architecture note. This is it: what the system is made of,
why each choice was made, and which PS capability each part answers. Where a
capability is not met, that is stated here rather than in a footnote.

**What it is.** An offline analyst workstation. FastAPI backend, vanilla HTML/JS frontend,
SQLite storage, one local model. It runs on a laptop with the network
disabled, which is the deployment PS 2.2.7 requires rather than an optimisation.

## Stack

| layer | choice | why this one |
|---|---|---|
| API | FastAPI + pydantic | typed request validation at the boundary |
| UI | vanilla HTML/CSS/JS | no build step, no CDN, nothing to fetch at run time |
| store | SQLite (`library.sqlite3`, `semantic_cache.sqlite3`) | embedded, file-backed, no service to run offline |
| vectors | FAISS `IndexFlatIP` | exact inner product; honest at this archive size |
| semantics | RemoteCLIP ViT-B/32 via `open_clip` | text and image in one space, runs on CPU |
| raster | rasterio | CRS, bounds and affine transform preserved on read |
| vision | OpenCV (RootSIFT + RANSAC), LightGlue weights staged | registration before differencing |

Model origins, licences and checksums: `PROVENANCE.md`.

## Pipeline

```
folder ─▶ INGEST ─▶ SCREEN+EMBED ─▶ INDEX ─▶ RETRIEVE ─▶ COMPARE ─▶ REVIEW ─▶ EXPORT
         sha256      RemoteCLIP      FAISS    filters     register    audit    provenance
         + CRS       + histogram     flat IP  + rank      + screen    trail
```

### Ingest — `app/main.py:_scan`, `app/tiling.py`

Recursive walk; GeoTIFF/COG, PNG and JPEG recognised. Each file gets a content
sha256 and a sidecar-metadata digest, so an unchanged file is skipped and a
changed one is detected even at identical size. CRS, bounds, affine transform
and available sensor/acquisition tags are preserved on GeoTIFF read. Optional
512 px windowed tiling keeps all source bands and pixels plus the parent
scene's hash, path and pixel window.

Missing georeferencing stays missing. The archive report consequently shows
fewer CRS-carrying scenes than total scenes, and that gap is the honest
signal about capture-derived imagery.

### Screen and embed — `app/semantic_clusters.py`

Scenes are screened before embedding: blanks, contact sheets, too-small
crops and duplicate captures of the same place and date are set aside.
Accepted representatives are embedded with RemoteCLIP and cached in
`scene_features`, keyed by a model-version string derived from the
checkpoint's own size and mtime — swap the checkpoint and every cached vector
is invalidated rather than silently reused.

### Index — two, on purpose

* **Semantic** — RemoteCLIP vectors, searched through a cached FAISS
  `IndexFlatIP`. This is the primary retrieval path for both free text and
  image-to-image.
* **Visual histogram** — `local-thumbnail-histogram-v1`, a deterministic
  48-bin RGB histogram (`_visual_fingerprint`). Arithmetic, not a model. It
  backs `/api/search/visual` as a transparent deterministic neighbour baseline
  and a compatibility fallback for archives indexed before the semantic path
  existed.

Keeping them separate is deliberate: a histogram is useful and reproducible,
but calling it a semantic embedding would be a false claim. `/api/index/status`
names the encoder so the distinction is visible in the product, not just the
docs.

Both are incremental. The histogram build selects only rows with no index
entry; the embedding cache is keyed per scene. Adding imagery costs only the
new imagery, which `benchmark_summary.json` records as a measured fact
(`incremental_old_vectors_unchanged: true`).

### Retrieve — `app/semantic_clusters.py:search`, `app/spatial.py`

Free text and image-to-image both rank by cosine similarity and label the
score `"RemoteCLIP cosine similarity"` rather than presenting it as a
confidence. AOI bounding box (WGS84), date range and exact sensor filters are
applied around the ranking; scenes with unknown georeferencing never match an
AOI, and antimeridian boxes must be split rather than silently wrapped.

### Compare — `app/verified_change.py`, `app/place_matching.py`

Before/after pairs are co-registered with RootSIFT + RANSAC first; a pair that
fails registration produces **no change conclusion** at all rather than a
noisy one. Differencing then runs on the registered overlap with bounded
per-channel normalisation and nuisance masks. Candidate regions are reported
in the reference image's analysis pixel coordinates and are explicitly not
geographic polygons or object detections.

### Review and export — `app/audit_routes.py`, `app/evaluation.py`

A ranked review queue, before/after evidence, confirm/reject decisions kept in
an audit trail, and exports that carry source-scene and processing provenance.
Registered analyses retain source snapshots, algorithm version, registration,
normalisation and quality evidence. `app/evaluation.py` exists to measure, and
its rule is that human judgments are never manufactured.

`app/local_llm.py` will use a local Ollama-compatible server for phrasing if
one happens to be running, and degrades to nothing if not. No cloud model is
ever contacted and no analytical conclusion depends on it.

## How this maps to the PS

| clause | where | state |
|---|---|---|
| 2.2.1 free-text + image-to-image retrieval, filters | `semantic_clusters.search`, `spatial.py` | met; quality measured in `BENCHMARK-REPORT.md` |
| 2.2.2 change analysis, change types, onset | `verified_change.py`, timeline | **partial** — screening and baseline-relative onset only; no validated construction / clearance / water / road classes, no appearance-disappearance-expansion-contraction form |
| 2.2.3 false-alarm suppression, quality | registration, nuisance masks, quality gate | met and measured: false alarms 116 → 74, precision 19.4% → 25.3%, recall 90.3% → 80.6% |
| 2.2.4 discovery and clustering | `semantic_clusters.py` | met; cluster purity and recall not measured against independent labels |
| 2.2.5 review queue, provenance, feedback | `audit_routes.py` | **partial** — queue, evidence, audit trail and provenance export present; queue priority is changed-fraction, explicitly **not** calibrated confidence; feedback reranking not wired |
| 2.2.6 incremental ingestion, on-prem, GeoTIFF/COG | `_scan`, `_build_index`, `tiling.py` | met, except differing GeoTIFF grids are **refused** rather than reprojected |
| 2.2.7 network-disabled demo, declared models | `run_offline.ps1`, `PROVENANCE.md` | met; 0 network attempts recorded in the frozen baseline |
| 2.3 deliverables | this file, `PROVENANCE.md`, `INDEX_BUILD.md`, `reality_check/` | architecture note, provenance, index procedure and the six operational facts present |

## Design rules this codebase holds to

1. **Never name a thing better than it is.** A histogram is called a
   histogram. A ranking score is called a similarity, not a confidence. A
   screening candidate is called a candidate, not a detection.
2. **Refuse rather than guess.** No registration, no change conclusion. No
   CRS, no AOI match. No date, no onset.
3. **Measure in the repository.** Every number quoted anywhere is regenerable
   by a script in `reality_check/`.
4. **Offline is a property, not a promise.** The frozen baseline asserts zero
   network attempts as a test artefact.

## Known gaps

Carried verbatim from `AUDIT-FIXES-2026-09-11.md` so that this note cannot be
read as a completion claim:

* Validated change classes and directional change form — not implemented.
* Calibrated confidence — not implemented.
* Independent held-out retrieval and change labels, and measured cluster
  purity/recall — not done.
* Reprojection and co-registration of differing GeoTIFF grids — refused.
* Licensed georeferenced multi-date AOI with real acquisition metadata — not
  obtained; capture-derived imagery cannot supply it.
* Wider-area scale, RAM and restart-resumable jobs — not measured.
