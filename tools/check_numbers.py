"""Fail if generated paper table values diverge from source result JSON."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
s=json.loads((root/'results/oscd_full_v2/summary.json').read_text(encoding='utf-8'))
t=(root/'tables/oscd_aggregate.tex').read_text(encoding='utf-8')
for key in ('pixel','remoteclip','gated_remoteclip'):
    m=s['methods'][key]
    for value in (f"{m['ap']:.3f}",f"{100*m['precision']:.1f}\\%",f"{100*m['recall']:.1f}\\%"):
        if value not in t: raise SystemExit(f'Missing/mismatched {key}: {value}')
if str(s['test_tiles']) not in t: raise SystemExit('Missing test tile count')
paper=(root/'paper/main.tex').read_text(encoding='utf-8')
for value in (str(s['test_tiles']),str(s['test_positives']),
              f"{s['methods']['pixel']['ap']:.3f}",
              f"{s['methods']['remoteclip']['ap']:.3f}",
              f"{s['methods']['gated_remoteclip']['ap']:.3f}"):
    if value not in paper: raise SystemExit(f'Paper text missing frozen result {value}')
for stale in ('169 test tiles','0.198','25.3\\%'):
    if stale in paper: raise SystemExit(f'Stale pilot result in paper: {stale}')
print('Paper aggregate table and LaTeX headline numbers match frozen results')
