"""Create an imagery-only import directory and honest demo instructions."""
import json
import shutil
from pathlib import Path
import rasterio

root=Path(__file__).resolve().parents[1]/'demo_data'/'same_location_false_alarm'
records=json.loads((root/'manifest.json').read_text())
dest=root/'IMPORT_THIS_FOLDER'
dest.mkdir(exist_ok=True)
lines=['# Same-location test pack','',
       'Import only IMPORT_THIS_FOLDER in Data Library. GeoTIFFs cover the same Knowledge Park II / Greater Noida area as the existing project imagery. Duplicate all-white RGB is excluded from import; original downloads remain preserved.',
       '','| Date | Candidate use | Local SCL cloud % | Local SCL shadow % |',
       '|---|---|---:|---:|']
grids=[]
seen=set()
for r in records:
    src=root/r['assets']['visual']['file']
    with rasterio.open(src) as ds:
        ds.read()
        grids.append((str(ds.crs),tuple(ds.transform),ds.width,ds.height))
    sha=r['assets']['visual']['sha256']
    if sha not in seen:
        shutil.copy2(src,dest/src.name)
        seen.add(sha)
    lines.append(f"| {r['date']} | {r['label']} | {r['local_scl_cloud_percent']} | {r['local_scl_shadow_percent']} |")
lines += ['',f'GeoTIFF grid consistency: {len(set(grids))} distinct grid(s) across {len(grids)} images.',
          '', 'Suggested comparisons:',
          '- February vs May: green vegetation versus brown/bare fields; inspect seasonal/crop effects. This is not a labelled no-change pair.',
          '- Clear date vs high local-cloud date: check that obscured ground is flagged for review, not declared destroyed or newly built.',
          '- February vs September 20: September includes local clouds and shadows; inspect those masked/uncertain areas rather than treating them as ground changes.',
          '- May vs September/October: inspect vegetation differences across seasons.',
          '', 'Limits:',
          '- These are real satellite acquisitions, not synthetic cloud or shadow edits.',
          '- SCL labels support inspection; they are not manually verified ground truth and are not automatically integrated into the app by importing RGB files.',
          '- No confirmed construction/no-change ground truth, dedicated isolated haze or illumination label, or snow example is claimed.',
          '- Sentinel-2 RGB is 10 m imagery; small buildings have less detail than Bhuvan display tiles.',
          '- Dates, source URLs and file hashes are recorded in manifest.json. Active archive was not modified.']
(root/'DEMO_GUIDE.md').write_text('\n'.join(lines),encoding='utf-8')
print('\n'.join(lines))
