# ANVESHAN — Operator Workflow & Data Plan

10 September 2026. Official PS reopened and re-read in browser for this document.

## Agreed development direction

- Build the application and its own frontend in **<repo>**.
- **earlier project notes** and **Downloads/anveshan** are reference/asset sources. Their architecture, UI, claims and written rules do not determine the new product. Reuse requires evidence of fit.
- Deliver software that an operator can use without writing code, invoking an AI coding assistant or running ingestion scripts for routine tasks.
- All essential runtime functions, model weights, UI assets and maps used in the demonstration must be local. Initial installation/staging can prepare the environment; the full demonstration must meet the PS's network-disabled constraint.
- Visual direction: restrained Army-oriented analyst workspace, readable and evidence-centred. Dark charcoal/olive, clear hierarchy and purposeful status colours are design preferences, not official requirements or security certification.
- The previous reality check established baseline failures. It does not prescribe retaining the old architecture or reducing the six official capabilities to avoid difficult work.

## Who asked, and what problem are we solving?

The description discusses an analyst searching a growing Earth-observation archive. It does not specify the exact operator rank, unit structure, installed hardware or production data-delivery system.

The core difficulty is that coordinate/date searches assume the analyst already knows where and when to look. The requested system must discover imagery by meaning, find similar sites, analyse meaningful changes through time, control false alarms and preserve evidence. Public or organiser-generated imagery will be used for evaluation.


## The complete user journey

**Open application → import an archive → inspect import quality → search/discover → compare dates → review candidates → record a decision → export evidence → add new acquisitions.**

The operator supplies images and intent. Software performs the repeated processing and keeps the record. Human review is for uncertain analysis, not a substitute for automated tiling, indexing, metadata handling or change detection.

| Operator's question | Why this matters | Software behaviour we should implement | Basis |
|---|---|---|---|
| How do I start it? | Routine use must not require developer tooling | Installed launcher starts the local service and opens the interface; show readiness or actionable startup errors | Product interpretation |
| Where do my images come from? | A search system needs an actual archive | Import supported locally available imagery; initial data staging is separate from offline analysis | PS ingestion/offline requirement |
| Can I add a whole folder? | One-by-one upload is impractical | Bulk import; recursive folder/manifest handling; file count, total bytes and validation preview | UI design implementing required ingestion |
| Are my files usable? | Bad metadata/imagery corrupt later results | Detect format, CRS, bands, acquisition metadata, source ID, duplicates and quality; show missing fields and errors before processing | PS metadata/quality requirement + design |
| Do I have to cut images into pieces? | Analysts should not prepare model inputs manually | Generate linked tiles/previews and embeddings automatically; preserve the original scene and its spatial mapping | Implementation responsibility |
| What if a large import takes hours? | Long jobs must remain understandable and recoverable | Background queue, progress, completed/failed counts, retry, persistent job state and restart recovery | Product design; exact throughput to measure |
| Can I search without knowing a place? | Discovery is the core use case | Text search and reference-image search over indexed imagery; ranked results with evidence thumbnails | Explicit PS |
| Can I restrict area, time and sensor? | Results must match the analyst's request | Actual geographic selection plus date/sensor filters; describe coverage and absent data | Explicit PS |
| How do I find similar places? | One discovery should lead to others | Similar-site action and embedding-based groups; distinguish alternate dates of one site from genuinely different sites | Explicit PS + design |
| What changed here? | Visual differences are not automatically meaningful | Align usable dated imagery, identify candidate changes, supported types and confidence; inspect before/after and a timeline | Explicit PS |
| How do I know it is not cloud or season? | False alarms waste review effort | Both-date validity/quality handling; explain rejection or uncertainty; do not force a fixed percentage of change | Explicit PS |
| When was it first visible? | Observation date differs from event date | Report first usable supporting evidence after establishing target change, last usable no-change evidence and gaps | PS + explanatory design |
| Can I accept/reject and return later? | Review work must persist | Save decision, note, linked evidence and audit entry; load previous decisions on reopening | Explicit PS |
| Can I give another analyst the evidence? | A report must be traceable | Export selection and decision with scene IDs, dates, geometry and processing provenance; readable report is a proposed convenience | Explicit provenance; report design |
| What happens tomorrow when new scenes arrive? | Archive grows continuously | Add new scenes incrementally, deduplicate, update available coverage/results, expose job status without a full rebuild | Explicit PS |
| Can it monitor a local incoming folder? | Avoid repeated manual selection | Optional configured watched-folder mode after reliable bulk import; no online service required | Optional design, not prescribed by PS |

## Bulk import: how “lakhs of images” should work

The PS requires efficient indexing and incremental ingestion but does **not** publish a million-image capacity requirement or a prescribed upload screen. “Images” may mean full scenes or small tiles; capacity claims must state which.

For the first local workstation version, the operator selects an accessible archive folder through the application and clicks **Scan**. A native folder picker or explicitly configured local data directory connects the browser UI to the local backend; a remote browser cannot silently select arbitrary server filesystem paths.

Scan results show file count, supported/unsupported formats, estimated input volume, detected dates/sensors, metadata gaps and duplicates. Missing metadata can be provided through a reusable import profile or a supported manifest; no routine script editing. Never fabricate a date or CRS to make import pass.

After **Import**, a persistent background job reads scenes in windows/batches, builds previews/tiles, records quality and provenance, computes embeddings, and appends to the index. The job stores which inputs finished. A restart should resume or safely retry without duplicating entries. A failed file should not silently corrupt the relationship between images, index entries and metadata.

The analyst sees **Ready / Processing / Failed / Needs metadata** and can review details. New arrivals go through the same flow. Installation, disk allocation and model updates may involve an administrator; routine imagery import and analysis should not.

Before claiming scale, measure scenes, tiles, input/storage volume, initial build time, incremental time, search latency, RAM and hardware. A tiny demo can demonstrate the mechanism; it cannot prove million-scene throughput.

## Offline website or desktop software?

An offline browser interface is a valid product shape: a locally installed backend serves the UI on the same machine, and inference/storage stay local. A desktop wrapper is another packaging option. The PS requires functionality and on-premises offline operation, not a particular wrapper.

Proposed first packaging: one-click local launcher + browser interface + local processing service + local data/model storage. A closed-LAN multi-user deployment can be considered later; the evaluation demo must still satisfy the stated network-disabled setup, so start with a self-contained machine.

No runtime dependency on online map tiles, Google Fonts/CDNs, cloud inference, online geocoding, external authentication or model downloads. An offline map may use staged permitted map data and the imported imagery itself. Offline does not automatically mean production security certification; access controls and deployment constraints must be based on actual requirements.

## Dataset findings and decisions

### Why the Sentinel-2 display looked blurred

Sentinel-2's visible bands have 10 m pixels. A 64×64 tile from those bands spans approximately 640×640 m. Enlarging that chip on screen enlarges pixels; it does not supply missing building or vehicle detail. Atmospheric conditions, colour stretch and display interpolation can further affect apparent quality. This is a data/task/display issue, not proof that Sentinel-2 is useless.

Source: [ESA Sentinel-2 band overview](https://step.esa.int/main/wp-content/help/versions/13.0.0/snap-toolboxes/eu.esa.opt.opttbx.s2msi.reader/Sentinel2Overview.html).

Large-scale vegetation, water or urban extent may be useful targets at that scale; small-object interpretation needs suitable resolution and validation. Keep the original scene, permit native-resolution zoom, show metres per pixel and use contextual imagery instead of enlarging a tiny model tile as the only evidence view.

Do not present generative sharpening as observed ground truth. AI-generated satellite-looking images can test UI behaviour, but they do not establish real retrieval/change performance. If “AI se images daalna” means an assistant downloaded real scenes, those remain real sources provided provenance is preserved.

### Was the Bhuvan screenshot attempt wrong?

It was useful for inspecting visible features and learning what better detail looks like. The inspected `gniot_2017.png` is visibly detailed and also contains a map pin, watermarks and a rendered date label. The stored manifest includes acquisition-period strings such as `2016-2012` and `2024-22`.

That screenshot is not equivalent to a source GeoTIFF: a clicked coordinate does not provide a transform for every pixel; display resampling, crop, scale, overlays and acquisition-period ambiguity affect quantitative comparison. The portal's stated source resolution does not independently verify the screenshot's metres per pixel. A year label is not an exact acquisition timestamp.

NRSC distinguishes imagery hosted for high-resolution visualisation from specific downloadable data products. Its Bhuvan service page mentions 1 m imagery for visualisation and AWiFS/LISS III products for free download. Therefore a sharp image visible in the viewer does not establish that the equivalent source raster is freely downloadable or licensed for every reuse. Check the particular product's metadata and permitted use. [NRSC service description](https://www.nrsc.gov.in/nrscnew/Services_Bhuvan_SatelliteDataServices.php) · [Bhuvan download documentation](https://bhuvan.nrsc.gov.in/wiki/index.php/Free_Satellite_Data_Download).

**Decision:** Retain screenshots as labelled references where appropriate. Build the core archive and time/area measurements around georeferenced source data with declared acquisition metadata and permitted use. A screenshot/reference-image search input is a useful separate function; it must not silently become authoritative dated geospatial evidence.

### What data should the product accept?

Separate the **demo dataset** we stage from the **ingestion capability** the delivered product provides. Software must accept new organiser-defined supported inputs, not just display images we manually prepared.

Start with well-defined GeoTIFF/COG input profiles, explicit band mapping and sidecar metadata support. Preserve originals, CRS/transform/footprint, scene identity, acquisition date or honest interval, sensor, pixel resolution, quality information and processing versions. UI should identify unsupported inputs and allow correction; it should not claim arbitrary optical/SAR/multispectral compatibility from accepting a filename alone.

Choose a demonstration dataset with sufficient detail for the selected concepts, multiple dates over matching footprints and independently reviewable positives/negatives. Keep the earlier OSCD/Noida experiments as baselines. A new high-resolution dataset still needs actual source, licence, dates, alignment and labels verified before selection. This document does not pretend that dataset has already been acquired.

## Our frontend's primary workspaces

1. **Data Library & Imports:** add folders, inspect metadata/coverage and manage jobs.
2. **Search & Discover:** text/image queries, real spatial/date filters, results and similar sites.
3. **Compare & Timeline:** large before/after view, native zoom, quality overlays, candidate changes and dated evidence.
4. **Review Queue:** confidence, explanations, accept/reject, notes and saved work.
5. **Reports & Provenance:** selected evidence exports and audit trail.
6. **System Status:** available disk, model readiness, queue health and local configuration.

The Army-oriented appearance supports these tasks. It should not obscure imagery, force green tint on evidence, imply calibrated confidence from a similarity score, or substitute decorative status badges for actual state.

## Development acceptance principle

For every proposed feature, answer: **Who uses it? What input do they have? What decision are they making? What does the software automate? What happens on failure? What evidence survives? Can the complete action run offline?**

First executable workflow should be **new folder → validation → import progress → searchable imagery → review → saved/exported evidence**, developed here. Change analysis and discovery remain core deliverables; early implementation order does not make them optional. Do not require the final operator to reproduce our developer experiments by terminal.
