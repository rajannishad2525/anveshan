# Index build and incremental ingestion

PS 2.3 requires the index-build and incremental-ingestion procedure as a
submission deliverable. PS 2.2.6 requires that newly acquired imagery can be
added *without a complete index rebuild*. This file is the procedure, and it
describes what the code actually does — every claim below is traceable to a
function named in it.

## 0. Staging (the only step that may touch a network)

Model weights must already be present before the application is started:

```
models/RemoteCLIP-ViT-B-32.pt          # semantic retrieval
models/sift_lightglue.pth              # registration
```

Origins, licences and checksums: `PROVENANCE.md`. The application never
downloads a model. If the checkpoint is missing, `app/semantic_clusters.py`
raises `"Offline RemoteCLIP checkpoint missing. Ask the installer to restore
it."` rather than fetching anything.

## 1. Start the workstation

```powershell
.\run_offline.ps1          # serves http://127.0.0.1:8765
```

The port is not a version marker; a newly started instance loads whatever code
is in this directory.

## 2. Import imagery

Data Library → **Archive intake**, or:

```
POST /api/scan   {"folder": "C:\\imagery\\mission_archive", "mode": "append"}
```

`mode` is the important argument and it defaults to appending:

| mode | effect |
|---|---|
| `append` | adds to the current archive; existing scenes are left alone |
| `replace` | calls `_reset_archive_for_new_import()` first — **this clears the archive** |

The UI exposes both as *Add to current archive* and *Use only this folder*.
Invalid folder paths are rejected *before* anything is cleared, so a typo
cannot destroy an archive.

Concurrency is guarded: an import or index build already in flight makes a
second request return `409` instead of interleaving.

### What import does per file

`_scan()` in `app/main.py`:

1. Walks the folder recursively, keeping files `_file_kind()` recognises
   (GeoTIFF/COG, PNG, JPEG).
2. Computes a **content sha256** (`_source_hash`) and a **metadata digest**
   over the file's `.json` sidecar and any `metadata.json` beside it.
3. Compares both against `scenes` and `intake_metadata`. A file whose content
   *and* sidecar are unchanged is skipped — re-running an import over the same
   folder is therefore a no-op, not a duplicate load.
4. A file whose content changed but whose size matched is detected by hash,
   its source identity and dimensions are refreshed, and its stale thumbnail
   index entry is invalidated.
5. For GeoTIFF/COG, CRS, bounds and affine transform are preserved, along with
   whatever sensor and acquisition tags exist. Folder-name year inference does
   not scan ancestor directories for accidental years.

Missing georeferencing is recorded as missing. It is never invented — which is
why `reality_check/ARCHIVE-REPORT.md` reports fewer CRS-carrying scenes than
total scenes.

### Optional tiling

Data Library can cut 512 px tiles from a GeoTIFF. Tiles preserve all source
bands and pixels, the CRS, the window transform, and the parent scene's hash,
path and pixel window. Originals stay available. Build the index afterwards.

## 3. Build the indexes

There are **two** indexes, deliberately separate, and they are built by
different calls.

### 3a. Visual histogram index — incremental by construction

```
POST /api/index/build
GET  /api/index/status
```

`_build_index()` selects only the rows that have no entry yet:

```sql
select s.id, s.path from scenes s
  left join scene_index i on i.scene_id = s.id
 where s.status = 'ready' and i.scene_id is null
```

Existing fingerprints are never read, rewritten or recomputed. **This is the
incremental-ingestion guarantee: adding imagery costs only the new imagery.**
The frozen baseline asserts it as a measured fact —
`incremental_old_vectors_unchanged: true` in
`reality_check/benchmark_summary.json`.

`encoder` reports `local-thumbnail-histogram-v1`. That is a deterministic
48-bin RGB histogram, not a learned embedding, and it backs
`/api/search/visual` only.

### 3b. Semantic index — RemoteCLIP embeddings

```
POST /api/clusters/build
GET  /api/clusters/status
```

`ClusterEngine` screens each scene, embeds the accepted ones with RemoteCLIP
and caches the vectors in `datasets/semantic_cache.sqlite3`:

* `scene_features(scene_id, vector, model)` — one row per embedded scene.
* The cache is keyed by a model version string built from the checkpoint's
  own size and mtime
  (`remoteclip-b32-screen-v1-<size>-<mtime_ns>`), so **swapping the checkpoint
  invalidates the cache automatically** and a stale vector can never be served
  as if it came from the new model.
* A cluster snapshot restores only when the archive signature (ids, paths,
  hashes, import times) and `INDEX_REVISION` both match. Any import
  invalidates it.

Screening does not embed everything: scenes judged blank, too small, or
duplicate captures of the same location and date are excluded. This is why
the archive report lists two different counts — every ready scene has a
histogram row, but only the accepted representatives carry an embedding, and
free-text search searches the smaller set.

### 3c. Search-time index

`semantic_clusters.py` builds a cached **FAISS `IndexFlatIP`** over the
embeddings — exact inner-product search, not an approximate index. Filters
(AOI bounding box, date range, sensor) are applied around it so that filtering
cannot silently drop hits that should have ranked. `IndexHNSWFlat` is used only
on the clustering and place-matching paths, never to answer a search query.

At the current archive size an exact scan is the honest choice; there is no
demonstrated large-scale ANN service here and the report does not claim one.

## 4. Verify

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=$env:TEMP\anveshan-pytest
.venv\Scripts\python.exe reality_check\archive_report.py --port 8773
```

`--basetemp` matters on this machine: the default pytest temp directory is
owned by another Windows account and every test errors with `WinError 5`
without it. With it, the suite passes (39 tests as of 12 September 2026).

`archive_report.py` regenerates `reality_check/ARCHIVE-REPORT.md` with the six
operational facts PS 2.3 asks for. It opens the operator archive **read-only**
and measures build time in a throwaway `ANVESHAN_DATA_DIR` sandbox, so running
it can never disturb a live archive.

## 5. Adding a new acquisition — the short version

```
POST /api/scan  {"folder": "<folder with the new scene>", "mode": "append"}
POST /api/index/build
POST /api/clusters/build
```

Unchanged files are skipped by hash. Only the new scene is fingerprinted and
embedded. No existing vector is rebuilt.

## Known gaps

These are real and must not be presented as solved:

* GeoTIFFs on **differing grids are refused** rather than reprojected. Mixed-grid
  organiser data will not co-register today.
* Scene screening decides what gets embedded; its purity and recall have not
  been measured against independent labels.
* Build time in the archive report covers the visual index only, not a full
  semantic re-embedding of the archive.
