# Audit follow-up — 11 September 2026

This is a scoped implementation record, not a claim that all 26 audit gaps are closed.

## Implemented and checked

- Tests use temporary databases, derived caches and logs via `ANVESHAN_DATA_DIR`; the operator archive is not opened by tests. Fixed legacy test-order assumptions.
- Import API defaults to append. The visible import selector preserves the prior **Use only this folder** workflow and adds **Add to current archive**. Invalid native folder paths are rejected before clearing. Active processing blocks import/clear conflicts.
- Reimport detects same-size content replacement by hash, refreshes source identity/dimensions, and invalidates the old thumbnail index entry.
- Building clusters is gated in the backend, not just localStorage. Completed cluster snapshots restore only for an identical active archive; imports invalidate them.
- WGS84 bounding-box and exact sensor filters are exposed in Search & Discover and applied before semantic ranking and temporal expansion. Unknown georeferencing is excluded from AOI results. Antimeridian AOIs must be split. This is a bounding-box filter, not arbitrary polygon selection.
- Upload search now passes date filters in the actual endpoint query parameters. Previously the UI sent them as multipart fields that the endpoint did not consume.
- GeoTIFF imports preserve CRS, bounds and affine transform, plus available sensor/acquisition tags. Folder year inference no longer scans ancestor UUIDs for accidental years.
- Optional 512-pixel GeoTIFF tile preparation is available in Data Library. Tiles preserve all source bands/pixels, CRS, window transform, parent source hash/path and pixel window. Originals remain available. Build the index afterwards. Repeated requests use a stable tile batch path.
- Search ranking uses a cached FAISS exact inner-product index instead of an individual SQLite lookup/dot product for every candidate. This remains exact linear vector search; it is not a demonstrated large-scale ANN service.
- Compare uses RootSIFT/RANSAC registration for PNG as well as other usable inputs, valid overlap, bounded robust per-channel normalization and nuisance masks. Existing GeoTIFF grid refusal remains. Failed registration produces no change conclusion.
- Candidate change regions are shown as boxes in the reference image's analysis pixel coordinates. These are not geographic polygons or semantic object detections.
- Build Timeline reports baseline-relative candidate onset, last usable no-change observation and unusable/missing-date gaps. It requires actual full dates; it does not infer exact capture order from folder ranges. It is not validated event onset or class-specific onset.
- Review Queue prioritizes unreviewed registered change candidates by changed fraction. The priority is explicitly not calibrated confidence.
- Registered analysis records retain source snapshots, algorithm version, registration, normalization and quality evidence. JSON exports include only processing records matching current source identities.

## Verification

- `python -m pytest -q --disable-warnings`: **29 passed**.
- JavaScript syntax checks passed for app, comparison and new audit controls.
- Synthetic shifted-image control yielded less than 1% adjusted difference; introduced local patch produced a localized candidate. These are implementation controls, not real-world accuracy validation.
- GeoTIFF tiling test compares every tile's pixels with its original window and checks CRS/source lineage.
- Live server restarted on 8773. The **21 scenes / 3 temporal groups** present before this update were restored; ready cluster status, AOI exclusion, review endpoint and processing-history export were checked.
- Browser Data Library renders import-mode and tile-preparation controls. Every browser interaction has not been exhaustively automated.

## Still open — do not mark complete

- Validated construction/clearance/water/road classes; directional appearance/disappearance/expansion/contraction. No class labels were invented from pixel colour or an LLM.
- Independent retrieval/change labels for this application, held-out performance, calibrated confidence, and measured cluster purity/recall. Preserved clusters were not silently relabelled.
- Real licensed georeferenced multi-date AOI and acquisition metadata. Software cannot recover missing original CRS/dates from screenshots reliably.
- Class-specific onset across persistent spatial regions; current onset is baseline-relative visual screening and can contain seasonal effects.
- Reprojection/co-registration of differing GeoTIFF grids; these remain refused. RGB nuisance masks and normalization need real cloud/season validation.
- Wider-area and organiser-data validation, scale/RAM/latency measurements, and restart-resumable in-progress jobs. Completed clusters persist; unfinished jobs do not automatically resume.
- Optional review feedback to retrieval reranking, code-formatting cleanup and repository/version-history setup.
- Broad dataset licensing/provenance packaging and model-class validation require actual supporting records and imagery.

Use `http://127.0.0.1:8773/` for the restarted application. Port numbers do not encode application versions; newly started instances load the code in this directory.
