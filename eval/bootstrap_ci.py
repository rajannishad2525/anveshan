"""Pair-cluster bootstrap of frozen test average precision; resample pairs, not tiles."""
import csv,json
from pathlib import Path
import numpy as np
from sklearn.metrics import average_precision_score

ROOT=Path(__file__).resolve().parents[1]
cfg=json.loads((ROOT/'configs/oscd_full.json').read_text(encoding='utf-8'))
rows=[r for r in csv.DictReader((ROOT/'results/oscd_full_v2/raw_tile_scores.csv').open(newline='',encoding='utf-8')) if r['split']=='test']
pairs=sorted({r['pair'] for r in rows})
assert len(pairs)==10
by_pair={p:[r for r in rows if r['pair']==p] for p in pairs}
rng=np.random.default_rng(cfg['seed'])
draws={m:[] for m in ('pixel','remoteclip')}
for _ in range(cfg['bootstrap_resamples']):
    selected=rng.choice(pairs,size=len(pairs),replace=True)
    sample=[r for p in selected for r in by_pair[p]]
    y=np.array([int(r['truth']) for r in sample])
    if len(np.unique(y))<2:continue
    for m in draws:
        draws[m].append(float(average_precision_score(y,np.array([float(r[m]) for r in sample]))))
out={'seed':cfg['seed'],'resamples_requested':cfg['bootstrap_resamples'],'unit':'OSCD pair',
     'n_pairs':len(pairs),'ap_95_percentile_ci':{m:[float(np.quantile(v,.025)),float(np.quantile(v,.975))] for m,v in draws.items()},
     'valid_draws':{m:len(v) for m,v in draws.items()}}
(ROOT/'results/oscd_full_v2/bootstrap_ci.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
