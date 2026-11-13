"""Compute exact prevalence baselines and a seeded random-ranking AP check."""
import csv, json
from pathlib import Path
import numpy as np
from sklearn.metrics import average_precision_score

ROOT=Path(__file__).resolve().parents[1]
cfg=json.loads((ROOT/'configs/oscd_full.json').read_text(encoding='utf-8'))
source=ROOT/'results/oscd_full_v2/raw_tile_scores.csv'
rows=list(csv.DictReader(source.open(newline='',encoding='utf-8')))
test=[r for r in rows if r['split']=='test']
y=np.array([int(r['truth']) for r in test])
if not len(test): raise SystemExit('No frozen test scores')
rng=np.random.default_rng(cfg['seed'])
sim=np.array([average_precision_score(y,rng.random(len(y))) for _ in range(cfg['random_rankings'])])
out={'n':len(y),'positives':int(y.sum()),'prevalence':float(y.mean()),
     'all_positive_precision':float(y.mean()),'random_pr_reference_line':float(y.mean()),
     'simulated_random_ap_mean':float(sim.mean()),'simulated_random_ap_sd':float(sim.std()),
     'random_rankings':cfg['random_rankings'],'seed':cfg['seed']}
(ROOT/'results/oscd_full_v2/random_baseline.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
