# ANVESHAN imagery archive

Built from **ANVESHAN-Data-Acquisition-Brief.pdf** (13 September 2026).

This folder replaces the current archive. The current one fails five PS clauses on properties of the
imagery, not the software: 0 of 165 scenes carry a real acquisition date, band 4 is an alpha channel
rather than NIR, 78 scenes carry no CRS, 0 declare a sensor, and all 16 locations sit in Greater Noida.

## Where imagery comes from

| Source | Res. | Bands | Format | Licence | Role |
|---|---|---|---|---|---|
| Bhoonidhi - ResourceSat-2A LISS-4 (bhoonidhi.nrsc.gov.in) | 5.8 m | G, R, NIR | GeoTIFF | Open (5 m and coarser) | **Primary archive.** ISRO satellite |
| Bhoonidhi - LISS-3 | 23.5 m | G, R, NIR, SWIR | GeoTIFF | Open | Wide-area context per AOI |
| Copernicus Sentinel-2 L2A (dataspace.copernicus.eu) | 10 m | B02/03/04, B08, SCL | COG | Free and open | Dense time series + real cloud mask |
| Cartosat 1-2.5 m | 1-2.5 m | - | - | Priced / restricted | Do **not** build the plan on this |
| Bhuvan screen captures | ~2 m | RGB only | PNG | Terms-of-use grey area | Demo appeal only, **not** the archive |

Both primary sources are named in PS 7.1, so neither has to be justified to a judge.

## AOIs

| # | Folder | Location | Centre | Demonstrates | PS clause | Set |
|---|---|---|---|---|---|---|
| 01 | `01_jewar_airport` | Noida International Airport, Jewar (UP) | 28.12N 77.55E | Farmland to runway and terminal, from 2021 | 2.2.2 construction / appearance | **core** |
| 02 | `02_dholera_sir` | Dholera SIR (Gujarat) | 22.24N 72.18E | A full road grid laid across salt flats | 2.2.2 road development | **extended** |
| 03 | `03_delhi_mumbai_expressway_dausa` | Delhi-Mumbai Expressway, Dausa segment | 26.9N 76.3E | 2019 to 2024 linear corridor across open land | 2.2.2 road (ideal for the transect tool) | **core** |
| 04 | `04_sardar_sarovar` | Sardar Sarovar reservoir (Gujarat) | 21.83N 73.75E | Reservoir filling and drawdown | 2.2.2 expansion / contraction | **core** |
| 05 | `05_sambhar_salt_lake` | Sambhar Salt Lake (Rajasthan) | 26.9N 75.1E | Seasonal wet to dry swing | 2.2.2 water-extent variation | **extended** |
| 06 | `06_singrauli_coalfield` | Singrauli coalfield (MP / UP) | 24.1N 82.6E | Forest to open-cast mine | 2.2.2 clearance / disappearance | **core** |
| 07 | `07_ludhiana_farm_belt` | Ludhiana farm belt (Punjab) | 31.01N 75.85E | Wheat to bare to paddy - scene changes, ground does not | 2.2.3 the negative set | **core** |
| 08 | `08_majuli_brahmaputra` | Majuli / Brahmaputra (Assam) | 26.88N 94.12E | Annual flood: water arrives and leaves | 2.2.3 temporary change | **extended** |
| 09 | `09_leh_himalaya` | Leh / Himalaya | 34.2N 77.6E | Seasonal snow cover | 2.2.3 snow confounder | **core** |
| 10 | `10_mundra_port` | Mundra Port (Gujarat) | 22.75N 69.7E | Harbour, quays, storage tanks | 2.2.1 semantic variety | **extended** |
| 11 | `11_jamnagar_refinery` | Jamnagar refinery (Gujarat) | 22.34N 69.86E | Heavy industrial | 2.2.1 + 2.2.4 clustering | **extended** |
| 12 | `12_corbett_forest` | Corbett / Western Ghats | 29.5N 78.9E | Continuous forest canopy | 2.2.1 forest class | **extended** |
| 13 | `13_thar_jaisalmer` | Thar desert (Jaisalmer) | 26.9N 70.9E | Dunes; strong shadow and illumination variation | 2.2.1 + 2.2.3 | **extended** |
| 14 | `14_chilika_lake` | Chilika Lake (Odisha) | 19.7N 85.3E | Coastal wetland | 2.2.1 | **extended** |

Three centres above differ from the brief's: 07, 08 and 11 were measured to point at the
wrong ground and were moved. `AOI-INDEX.csv` is authoritative; `CORRECTIONS.md` shows the
measurements. Core set = 1, 3, 4, 6, 7, 9 (the brief calls this "the core five"; the table marks six rows).
Do not skip **07 Ludhiana** - it is the single most valuable acquisition in the list.

## Per-AOI layout

```
NN_location/
  liss4/            5.8 m Bhoonidhi ResourceSat-2A - primary
  liss3/            23.5 m wide-area context
  sentinel2_l2a/    10 m COG, B02/03/04/08 + SCL
  bhuvan_capture/   PNG demo visuals only
  sidecar/          one JSON per scene (see MANIFEST-TEMPLATE.json)
  _raw_download/    untouched vendor originals
  _AOI.md           centre, clause, target dates, checklist
```

Plus, at this level:
- `_heldout_punjab_seasonal/` - the held-out negative set, never used for tuning
- `_reprojected_common_grid/` - step-1 output, what the app actually ingests
- `_tools/` - the acquisition scripts (below)
- `AOI-INDEX.csv`, `MANIFEST-TEMPLATE.json`, `CORRECTIONS.md`

## Tools

```
python _tools/fetch_sentinel2.py --aoi 7                  # 6 clear + 2 hazy dates
python _tools/fetch_sentinel2.py --aoi 7 --dry-run        # list first, download nothing
python _tools/make_contact_sheet.py --aoi 7               # true colour over NDVI strip
```

`fetch_sentinel2.py` needs no account and no API key. It reads a windowed 1024x1024 crop
out of each Cloud Optimized GeoTIFF over HTTPS, so one date costs about 6 MB instead of
the ~800 MB a full granule would. Catalogue: `https://earth-search.aws.element84.com/v1`.
Pixels: `https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/...`.

Two behaviours worth knowing:
- A tile whose centre is near a granule edge comes back mostly empty. Tiles over
  `--max-nodata` (default 2%) are deleted and replaced with the catalogue scene nearest
  in time, so the temporal spread survives the substitution.
- Reflectance is `DN * 0.0001`. Do **not** subtract 1000 - see `CORRECTIONS.md`.

## Specification every scene must meet

| Property | Requirement |
|---|---|
| Format | GeoTIFF or COG. PNG/JPEG screen captures do not qualify (PS 2.2.6) |
| CRS | Embedded in the file (UTM or the product's native projection) |
| Acquisition date | Real `YYYY-MM-DD` in metadata or sidecar. A four-year folder label is not a date |
| Bands | NIR mandatory. LISS-4: G, R, NIR. Sentinel-2: B02, B03, B04, B08 + SCL |
| Tile size | 512x512 or 1024x1024. 256 px was measured unreliable for change typing |
| Dates per location | 6-8, spanning before / during / after |
| Grid consistency | One CRS per AOI, ideally one pixel grid |
| Cloud and haze | Keep 2-3 hazy or partly clouded scenes per AOI on purpose |
| Seasonal pairs | Four seasons of the Punjab belt, held separately |
| Sidecar metadata | datetime, sensor, bands, CRS, source, licence - per scene |

## Order of work

1. **Blocking:** GeoTIFF reprojection onto a common grid (1-2 days, rasterio already a dependency).
   Nothing acquired can be ingested until this exists.
2. Core AOIs 1, 3, 4, 6, 7, 9 from Bhoonidhi LISS-4, 6-8 dates each (1-2 days).
3. Punjab seasonal set, downloaded separately, kept out of tuning (half a day).
4. Sentinel-2 L2A over the same AOIs where a denser series helps (1 day).
5. Only then: confidence scoring, tile-level change typing, held-out evaluation.

## The trade-off, stated openly

LISS-4 at 5.8 m looks less sharp than the ~2 m Bhuvan captures currently on screen. That is the right
trade: LISS-4 carries a real acquisition date, an embedded CRS and a near-infrared band, and the PS
asks for all three. Keep the Bhuvan captures as demonstration visuals; build the archive on LISS-4.
