# Same-location correction — current implementation

Section 2.2.2 covers multi-temporal analysis of an area. Section 2.2.4 separately requires discovery of comparable sites across locations. Section 2.2.7 permits public pretrained models with declared provenance/licence and staged offline weights. No LLM-specific prohibition was found; external cloud/API dependence during evaluation is prohibited.

The Clusters page now has two views:
- **Same-location timelines:** coordinates establish common footprints when available. Without them, RootSIFT mutual feature matches + RANSAC check structural correspondences, spatial distribution and image overlap. RemoteCLIP/FAISS only retrieves candidates; a 0.90 global similarity cutoff no longer splits a timeline because of seasons/construction.
- **Similar sites:** embedding-based grouping of representatives from different site timelines. These are not presented as temporal change pairs.

On the current archive of 123 records, the corrected pipeline produces **10 location timelines, each with 5 usable periods**. It hides 50 same-period duplicate copies and withholds 23 records (20 blank/low-detail, 2 Bhuvan placeholder logos, 1 contact sheet). Blank 2025/2026 downloads do not become observations. Different dated observations with identical pixels remain distinct; the system must not silently remove evidence of no change. Folder labels such as `2024-22` are shown as 2022–2024, not an invented precise acquisition date.

**Coordinate-free evaluation:** on 50 usable images, the initial SIFT/RANSAC matcher produced 30 same-group pairs; all agreed with the reference tile IDs, but only 30 of 100 available reference pairs were recovered (30% pair recall). Tile IDs are weak fixture labels, not independently verified ground truth; this is a development evaluation, not a held-out accuracy claim. Some true locations remain split without metadata. See `datasets/place_visual_only_evaluation.json`. A LightGlue experiment is being evaluated separately; it must not be called deployed until its measurements justify integration.

Ten focused tests passed. Headless Chrome verified 10 timelines, 5 images in the timeline gallery, the separate similar-site view (2 groups), and its image gallery, without JavaScript errors. OpenCV 4.13.0.92 was staged into the project environment; its additional dependency is declared in `requirements-clustering.txt`.

**99% across future archives has not been achieved or measured.** Current coordinate-based completeness must not be represented as coordinate-free recognition accuracy. Screening/generalisation to arbitrary logos, SAR, multispectral imagery, and million-image performance remain unvalidated. The operator workflow stays automatic: import folder → background processing → inspect results.

---
# Historical first attempt — superseded by the correction above

# Automatic satellite clustering — 10 September 2026

The application now uses the installed RemoteCLIP checkpoint to screen images and compute actual visual embeddings. The previous `/api/clusters` implementation grouped filenames; it did not recognise image content. Routine use is **import folder → automatic background processing → Clusters → inspect/compare**. No terminal, coding, prompt entry or manual cluster construction is required.

## Research and implementation choice

- [RemoteCLIP official implementation](https://github.com/ChenDelong1999/RemoteCLIP) documents local OpenCLIP-compatible checkpoints and normalised image/text embeddings. We load the existing ViT-B-32 weights; no model download is initiated by the application.
- [FAISS official index documentation](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes) explains normalised-vector similarity and HNSW approximate neighbour search. FAISS finds candidates; it does not establish their geographic identity.
- [DBSCAN documentation](https://scikit-learn.org/stable/modules/clustering.html#dbscan) explains density-connected groups and noise. Density connectivity alone does not require every pair of members to be similar. This implementation instead applies an all-member similarity check to FAISS candidates, preventing loose neighbour chains from merging groups.

Processing: readable image → blank/contact-sheet check → RemoteCLIP satellite/non-satellite prompt screening → cached normalised embedding → FAISS HNSW neighbours → minimum pairwise cosine 0.90 → geographic contradiction veto → visible groups and separate withheld/unmatched images.

The screening thresholds (positive similarity >= 0.20 and margin >= 0.015) and grouping threshold are provisional engineering settings. Neither is an accuracy percentage or calibrated confidence. Filenames do not determine membership. GeoTIFF bounds are read from the files: conflicting known footprints veto a match. Matching embedded bounds establish agreement of the supplied georeferencing, not independent ground-truth verification. Images without georeferencing retain an unverified location label.

## Observed current archive result

Final live-server run on 123 records:

| Result | Records |
|---|---:|
| Accepted unique satellite candidates | 27 |
| Exact decoded-image duplicate copies hidden | 27 |
| Withheld for screening/quality review | 69 |
| Accepted candidates without a group | 23 |
| Displayed groups | 2, with 2 images each |

The 69 withheld records include 20 blank/low-detail records, one very wide contact sheet, and 48 non-satellite-or-uncertain screening decisions. **That last category includes valid satellite imagery: screening recall remains inadequate. It must not be reported as 48 correctly rejected non-satellite images.**

Both actual Bhuvan logo placeholder records (scene IDs 122 and 123) were withheld and absent from every group. Initial embedding-only groups also mixed different geographic tiles; the georeferencing veto removed those groups. The final two groups show matching embedded footprints with minimum pair similarity 0.9349 and 0.9334. These two pairs cannot establish 99% precision on future archives.

## Verification and remaining work

- Five focused tests passed: neighbour-chain prevention, unrelated-image noise, similar-image grouping, empty archive, and conflicting geographic extents.
- Live API checks confirmed actual logo exclusion and PNG previews for GeoTIFF originals.
- Headless Chrome checked automatic progress, two final groups, opening the gallery and loaded imagery; no JavaScript errors were reported.
- Features are cached in `datasets/semantic_cache.sqlite3`; groups/index are reconstructed in memory. The current machine runs CPU inference. Million-image throughput and SAR/multispectral generalisation have not been validated.

**The 99% target is not achieved or validated.** Next accuracy work needs a separately labelled, representative evaluation set, including different places that look alike, the same place across seasons, logos, diagrams, bad tiles and imagery from different sensors. Measure pair precision, missed-match recall, screening false acceptance and coverage separately. Freeze thresholds before the held-out test. Improve the screening model and add image registration/local-feature verification for images without reliable georeferencing. This is engineering/evaluation work; operators should continue to use the GUI, not run models themselves.

The old Search & Discover histogram/metadata retrieval is a separate path; this change does not claim that it has become semantic text search.
