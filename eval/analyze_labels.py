"""Compare two blind reviewer CSV exports; never invent missing labels.

Usage: python eval/analyze_labels.py reviewer1.csv reviewer2.csv
"""
import csv,json,sys
from pathlib import Path
from sklearn.metrics import cohen_kappa_score

if len(sys.argv)!=3: raise SystemExit(__doc__)
def read(path):
    rows=list(csv.DictReader(Path(path).open(newline='',encoding='utf-8')))
    if not rows: raise SystemExit(f'No labels: {path}')
    mapping={}
    for r in rows:
        key=(r['query_id'],r['candidate_id'])
        if key in mapping:raise SystemExit(f'Duplicate judgment {key} in {path}')
        if r['label'] not in ('0','1','u'):raise SystemExit(f'Invalid label {r["label"]}')
        mapping[key]=r['label']
    return mapping
a,b=read(sys.argv[1]),read(sys.argv[2])
if set(a)!=set(b):raise SystemExit(f'Reviewers judged different candidate sets: {len(set(a)^set(b))} mismatches')
keys=sorted(a)
usable=[k for k in keys if a[k]!='u' and b[k]!='u']
if not usable:raise SystemExit('No jointly usable binary labels')
out={'items_total':len(keys),'items_binary_both':len(usable),
     'items_uncertain_either':len(keys)-len(usable),
     'raw_agreement':sum(a[k]==b[k] for k in usable)/len(usable),
     'cohen_kappa':float(cohen_kappa_score([a[k] for k in usable],[b[k] for k in usable])),
     'disagreements':[{'query_id':k[0],'candidate_id':k[1],'reviewer_1':a[k],
                       'reviewer_2':b[k]} for k in keys if a[k]!=b[k]]}
print(json.dumps(out,indent=2))
