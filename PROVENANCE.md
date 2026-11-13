# Model and dataset provenance

PS 2.2.7 requires that any pretrained public model declare its origin and
licence and that the weights be packaged for offline use. PS 2.3 requires
model and dataset provenance as a submission deliverable. This file is that
declaration.

Checksums were computed on 12 September 2026 from the files actually staged in
this repository. Anything not independently verified is marked as such rather
than asserted.

## Models staged locally

| file | bytes | sha256 |
|---|---|---|
| `models/RemoteCLIP-ViT-B-32.pt` | 605,208,421 | `60014e395d930a3f2963d1d89c8522bf4ad56775571e4356e866864789af85c4` |
| `models/sift_lightglue.pth` | 47,632,573 | `5b52b8d9982d43532dc042606b346bb9594c9f5a4bd6f64362c63866287b4ac0` |

### RemoteCLIP ViT-B/32 — semantic retrieval

* **Role.** The only learned model on the retrieval path. Encodes both the
  free-text query and every archive tile into a shared embedding space;
  `/api/search/semantic` ranks by cosine similarity over these embeddings and
  reports `score_type: "RemoteCLIP cosine similarity"`.
* **Origin.** <https://github.com/ChenDelong1999/RemoteCLIP>, distributed
  through the Hugging Face repository `chendelong/RemoteCLIP`. The staged path
  the earlier baseline scripts resolve
  (`models/models--chendelong--RemoteCLIP/snapshots/...`) is the Hugging Face
  cache layout, which records that the checkpoint came from that repository.
* **Licence.** Apache-2.0 (source repository's declared licence).
* **Loaded by.** `app/semantic_clusters.py`, through `open_clip` with
  `ViT-B-32` and `pretrained=None`, then `load_state_dict` from the local file.
  The architecture is OpenCLIP's; only the weights are RemoteCLIP's.
* **Offline packaging.** The weights sit in `models/` inside this repository.
  The loader raises `"Offline RemoteCLIP checkpoint missing. Ask the installer
  to restore it."` rather than downloading anything. No code path in the
  application initiates a model download.
* **Known limitation.** This is the ViT-B/32 variant, the smallest RemoteCLIP
  checkpoint. Retrieval quality is reported in `reality_check/BENCHMARK-REPORT.md`
  and is not claimed to match larger variants.

### SIFT + LightGlue — image registration

* **Role.** Co-registration of before/after pairs before any change screening,
  so that misregistration is not reported as change (PS 2.2.3). Used alongside
  the RootSIFT/RANSAC path in `app/place_matching.py`.
* **Origin.** LightGlue, <https://github.com/cvg/LightGlue> (Computer Vision
  and Geometry Group, ETH Zürich). The staged file is the SIFT-variant weight.
* **Licence.** Apache-2.0 (source repository's declared licence).
* **Status.** Evaluated, not yet presented as the deployed matcher — see
  `CLUSTERING-REALITY-CHECK.md`, which states it must not be called deployed
  until its measurements justify integration.

### Not a model

`local-thumbnail-histogram-v1` — the encoder named by `/api/index/status` — is
a deterministic 48-bin RGB thumbnail histogram computed in
`app/main.py:_visual_fingerprint`. It is arithmetic, not a learned model, has
no weights and no licence. It backs `/api/search/visual` as a transparent
deterministic baseline. It is deliberately kept separate from the semantic
path and must never be described as an embedding.

## Datasets

### OSCD — Onera Satellite Change Detection

* **Role.** The labelled change / no-change set behind every change number in
  `reality_check/BENCHMARK-REPORT.md` (169 tiles; 31 positive, 138 negative).
* **Origin.** Sentinel-2 image pairs with human change masks, published by
  Daudt, Le Saux, Boulch and Gousseau. Consumed here as parquet splits
  (`data/oscd/data/train-*.parquet`, `test-*.parquet`).
* **Protocol, exactly as run** (`reality_check/run_baseline.py`): calibration on
  the first 3 train pairs, evaluation on the first 3 test pairs, all complete
  64 px tiles; a tile counts as positive when the OSCD mask covers more than
  2% of it.
* **Licence.** Not independently re-verified for this document. Confirm the
  current OSCD distribution terms before submission and record them here.
* **Stated limitation.** Already recorded in `BENCHMARK-REPORT.md`: this is
  public data the project has already used, so it is not pristine
  organiser-held-out evaluation, and tile-level masks do not validate
  operational change classes.

### Bhuvan (NRSC / ISRO) captures

* **Role.** Indian-area imagery for the operator demonstration.
  `datasets/knowledge_park2_river_bhuvan`, `datasets/bhuvan_source_check`.
* **Origin.** NRSC / ISRO Bhuvan open Earth-observation data, named in the
  problem statement's own source list (PS 7.1).
* **Caveat that must not be dropped.** These are manual captures, not
  downloaded licensed data products. Acquisition CRS and exact dates cannot be
  reliably recovered from a capture, which is why 78 of 165 archive scenes
  carry no declared CRS (see `reality_check/ARCHIVE-REPORT.md`). They are
  usable for demonstrating the workflow; they are not a substitute for a
  licensed georeferenced product.
* **Excluded on purpose.** A bulk-automated capture set produced elsewhere was
  never staged: automating against Bhuvan's interface would breach its terms of
  use, which is a live compliance question for a government-use
  deployment. Only coordinates were retained, as approximate waypoints.

### Temporal GeoTIFF tiles

* **Role.** The georeferenced part of the archive — 256×256, 4-band,
  EPSG:3857 tiles under `datasets/import_batches/*/docx_temporal/`, organised
  by acquisition period (2012-2016 through 2026).
* **Status.** These carry a declared CRS, bounds and affine transform, which is
  what makes area measurement and AOI filtering possible at all.
* **Licence.** Depends on the underlying source for each capture; record it per
  batch before submission.

## What the application does at run time

* No model is downloaded, ever. Weights must already be in `models/`.
* No dataset is fetched. Imagery is read from a local folder the operator
  chooses.
* The frozen baseline records **0 network attempts**
  (`reality_check/benchmark_summary.json`).

## Open items

1. Confirm and record the OSCD distribution licence.
2. Record per-batch licensing for the `docx_temporal` captures.
3. If the retrieval encoder is ever changed, update the table above — the
   checksum is the only thing that proves which weights produced a given
   number.
