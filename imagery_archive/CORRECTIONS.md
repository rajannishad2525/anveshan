# Corrections to the acquisition brief

Everything here was measured against real pixels on 13 September 2026, not reasoned from
the brief. Each entry says what the brief specifies, what the imagery actually shows, and
what was changed. PS 2.3 asks for dataset provenance as a submission deliverable; this is
part of it.

---

## 1. AOI 07 centre pointed at Ludhiana city, not the farm belt

**Brief:** 30.90N 75.85E, "Ludhiana farm belt (Punjab)", the negative set for PS 2.2.3.

**Measured**, scene `S2A_43REQ_20240206_0_L2A`, 6 February 2024, peak wheat season:

| centre | NDVI median | SCL vegetation |
|---|---|---|
| 30.90N 75.85E (brief) | 0.15 | **0.2%** |
| 30.90N 75.725E | 0.47 | 45.7% |
| 30.90N 75.975E | 0.80 | 78.9% |
| **31.01N 75.85E** | **0.88** | **95.6%** |
| 30.79N 75.85E | 0.83 | 77.9% |
| 31.05N 75.68E | 0.86 | 95.9% |

30.90N 75.85E is Ludhiana city centre. In the middle of the wheat season it reads as 99.8%
not-vegetated, because SCL class 5 covers built-up as well as bare soil.

**Why it mattered:** the brief calls this "the single most valuable acquisition in the
list", because seasonal suppression can only be demonstrated where the scene changes and
the ground does not. A city changes neither. The acquisition would have produced eight
dates that prove nothing.

**Changed:** `AOI-INDEX.csv` centre for AOI 07 to **31.01N 75.85E**, 12 km north, still
within the Ludhiana farm belt. The eight scenes downloaded at the old centre were deleted
and re-fetched.

Result at the corrected centre:

| date | NDVI | veg | bare | cloud/shadow |
|---|---|---|---|---|
| 2024-01-17 | 0.03 | 0.0% | 50.5% | 47.8% (deliberate hazy scene) |
| 2024-02-06 | 0.84 | 78.8% | 18.8% | 0.0% (wheat, peak green) |
| 2024-04-06 | 0.57 | 65.4% | 32.5% | 0.0% |
| 2024-05-21 | 0.13 | 3.1% | 95.2% | 0.0% (post-harvest bare) |
| 2024-10-13 | 0.49 | 51.5% | 46.1% | 0.0% (paddy) |
| 2024-11-22 | 0.14 | 0.0% | 97.0% | 0.0% |
| 2024-12-17 | 0.29 | 0.0% | 96.3% | 0.0% |
| 2024-12-22 | 0.38 | 3.7% | 92.6% | 0.0% |

---

## 2. The BOA reflectance offset is already applied - do not subtract it again

**The trap:** Sentinel-2 processing baseline 04.00 and later carry `BOA_ADD_OFFSET = -1000`,
and the STAC item repeats it: `raster:bands = {scale: 0.0001, offset: -0.1}`. The obvious
reading is that 1000 must be subtracted before computing NDVI.

**Measured**, NIR digital number over deep water at Sardar Sarovar (21.83N 73.75E), where
true NIR reflectance is near zero:

| scene | baseline | `boa_offset_applied` | NIR DN median |
|---|---|---|---|
| `S2A_43QCE_20210119_0_L2A` | 02.14 | False | 0 |
| `S2B_43QCE_20240201_0_L2A` | 05.10 | True | 359 |

If the offset were still outstanding, the 2024 scene would read ~1000 over water. It reads
359. The offset is already baked into the sentinel-cogs pixels.

**Consequence if ignored:** subtracting 1000 drives red reflectance negative over
vegetation and inflates NDVI. On the 6 February Ludhiana scene, median NDVI reads 0.17
correctly and **0.65** with the offset wrongly re-applied - a difference large enough to
turn a bare field into a healthy crop.

**Changed:** every scene now carries `REFLECTANCE_FORMULA = "reflectance = DN * 0.0001
(do NOT subtract 1000)"` in both the GeoTIFF tags and the sidecar JSON, alongside
`boa_offset_applied` and `processing_baseline`.

---

## 3. Granule-edge tiles came back mostly empty (bug in the fetcher, now fixed)

A STAC bbox match only proves the AOI *centre* falls inside a granule footprint. The
1024x1024 tile extends 5 km in every direction and can run off the edge.

**Measured** at AOI 04 (Sardar Sarovar), 2023-2024 window: four of the selected scenes came
back 61-66% nodata. At the brief's centre on `2024-03-19`, the tile was **71% nodata**.

**Changed:** `fetch_sentinel2.py` now computes nodata from SCL class 0, deletes any tile
over `--max-nodata` (default 2%), and substitutes a replacement.

A second defect surfaced during that run: the first version took the head of the reserve
list, so all four substitutions landed in January 2023 and collapsed the temporal spread
the brief requires ("6-8 dates spanning before, during and after"). Substitution now picks
the reserve scene **nearest in time** to the rejected one.

---

## 4. A retracted finding: AOI 12 Corbett is fine

An earlier pass flagged the Corbett centre as a weak forest exemplar at 55.9% vegetation.
That was wrong. Each candidate had been sampled from its own lowest-cloud scene, so a
May scene was being compared against December ones and the dry season was doing the work.

Re-tested with **one scene for all candidates**, `S2B_44RKT_20241211_0_L2A`, 11 December 2024:

| centre | NDVI median | SCL vegetation |
|---|---|---|
| **29.50N 78.90E (brief)** | **0.85** | **97.4%** |
| 29.53N 78.77E | 0.78 | 63.1% |
| 29.55N 78.70E | 0.79 | 70.7% |
| 29.58N 78.75E | 0.78 | 56.3% |

The brief's centre is the best of the four. No change made.

Separately, the brief labels this row "Corbett / Western Ghats". Corbett is in Uttarakhand;
the Western Ghats are roughly 1500 km southwest. The coordinates are Corbett's and they are
good; only the label is confused.

---

## 5. AOI 11 Jamnagar centre moved to the refinery

**Brief:** 22.35N 70.00E, "Jamnagar refinery (Gujarat)", heavy industrial for PS 2.2.1.

An earlier attempt at this comparison failed: granule `42QXK` returns 100% nodata at
69.86E, so the candidates were not imaged by the same granule. Re-run by giving each
candidate the best scene that fully covers *it*, all of which happened to be 31 October 2024:

| centre | NDVI median | bare / built | vegetation | nodata |
|---|---|---|---|---|
| 22.35N 70.00E (brief) | 0.56 | 30.1% | 59.8% | — |
| **22.34N 69.86E** | 0.39 | **58.4%** | 38.6% | 0% |
| 22.33N 69.84E | 0.47 | 48.0% | 49.1% | 0% |
| 22.39N 69.90E | 0.38 | 55.9% | 39.5% | 0% |

The brief's centre reads as majority vegetation; the Reliance complex sits about 15 km
west. SCL class 5 covers built-up as well as bare soil, so 58.4% at 69.86E is the
industrial signature, with the planted green belt accounting for the remaining 38.6%.

**Changed:** AOI 11 centre to **22.34N 69.86E**.

---

## 6. AOI 08 Majuli centre moved onto a channel

**Measured**, one scene for all candidates, `S2A_46RFQ_20241228_0_L2A`, 28 December 2024:

| centre | SCL water |
|---|---|
| 26.95N 94.20E (brief) | 2.2% |
| 26.90N 94.20E | 18.0% |
| **26.88N 94.12E** | **22.0%** |

"Annual flood: water arrives and leaves" cannot be shown on a tile that is 97.8% land.

**Changed:** AOI 08 centre to **26.88N 94.12E**.

---

## 7. Two more fetcher defects, both found by checking the output

**Filename collisions across AOIs.** Scenes were named `<date>_s2_<flag>.tif`, so three
different AOIs imaged on 2 January 2023 produced three files called
`2023-01-02_s2_clear.tif`. Scanned into the application, scenes are listed by filename
alone - an operator could pair Ludhiana with Leh without noticing. Names now carry the AOI:
`AOI07_2024-02-06_s2_clear.tif`. 144 already-downloaded files were renamed.

**A rejection could delete a good tile.** Adjacent orbits image the same point on the same
day, and both scenes reduced to one filename. The second overwrote the first; when the
second was then rejected for granule-edge nodata, its `unlink()` removed the good tile as
well, leaving a sidecar with no raster. Found once, in the held-out set
(`HELDOUT_2024-09-23_s2_clear`), and re-fetched. An archive-wide check found no other case:
121 rasters, 121 sidecars, 1:1. Same-day duplicates are now disambiguated before writing
rather than overwritten.

---

## 8. Where the archive is honestly weak

**AOI 04 Sardar Sarovar shows only a modest water swing.** Measured across its eight dates,
SCL water ranges 16.1% (January 2023) to 8.2% (December 2024), and NDWI-positive area stays
between 14.9% and 18.7% throughout. That is a real expansion/contraction signal but roughly
a factor of two, not a dramatic one. Sardar Sarovar is a narrow river-valley reservoir, so a
10 km tile is mostly hillside whatever the water level; no candidate centre tested carried
more than 9.8% water. Treat this AOI as the weakest of the three water examples.

For contrast, the two that came out strong:

| AOI | signal | range across the eight dates |
|---|---|---|
| 09 Leh | SCL snow | 89.1% (Feb 2024) to 0.0% (Jul, Aug, Sep) |
| 05 Sambhar | SCL water | 17.5% (Jan) to 0.0% (May), NDWI 16.0% to 0.1% |

AOI 05 carries all eight dates inside 2023 rather than spanning both years, because monsoon
scenes are cloudy and lose the clear-scene selection. The wet-to-dry swing is still captured.
