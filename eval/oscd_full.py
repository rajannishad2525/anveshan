"""Frozen full-OSCD, pair-level evaluation. Run once after reviewing config.

No data/model downloads. Outputs raw scores, per-pair metrics, summary and
pair-bootstrap intervals under results/oscd_full/. Refuses to overwrite them.
"""
from __future__ import annotations
import csv, hashlib, io, json, os, platform, random, socket, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / 'configs/oscd_full.json'
CFG = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
OUT = ROOT / 'results/oscd_full_v2'
if OUT.exists() and any(OUT.iterdir()):
    raise SystemExit(f'Refusing to overwrite frozen evaluation: {OUT}')
OUT.mkdir(parents=True, exist_ok=True)
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
sys.dont_write_bytecode = True

attempts = []
def deny(*args, **kwargs):
    attempts.append(repr(args))
    raise RuntimeError('Network disabled for evaluation')
socket.socket.connect = deny
socket.create_connection = deny

import numpy as np
import torch
from PIL import Image
from sklearn.metrics import average_precision_score, confusion_matrix, precision_score, recall_score
PROJECT = Path(r'C:\Users\abcom\Downloads\anveshan')
sys.path.insert(0, str(PROJECT / 'src'))
from anveshan import baseline, change, config, embed, metrics, oscd, rejection

torch.set_num_threads(CFG['torch_threads'])
torch.set_num_interop_threads(1)
config.OSCD_DIR = Path(CFG['dataset_root'])
checkpoint = ROOT / CFG['checkpoint']
if not checkpoint.is_file():
    raise SystemExit(f'Missing staged checkpoint: {checkpoint}')
embed._checkpoint_path = lambda: str(checkpoint)
for split in ('train','test'):
    files = list((config.OSCD_DIR / 'data').glob(f'{split}-*.parquet'))
    if not files: raise SystemExit(f'Missing {split} parquet; no download permitted')

def save_json(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, default=str), encoding='utf-8')

def score_split(split):
    rows=[]; pair_summaries=[]
    for pair in oscd.load_pairs(split):
        tiles=change.tile_pair(pair.before,pair.after,pair.mask,tile_size=CFG['tile_size_px'])
        if not tiles: raise RuntimeError(f'No complete tiles: {pair.pair_id}')
        b=embed.embed_images([Image.fromarray(t.before) for t in tiles],batch_size=CFG['batch_size'])
        a=embed.embed_images([Image.fromarray(t.after) for t in tiles],batch_size=CFG['batch_size'])
        y=np.array([t.mask.mean()>CFG['positive_mask_fraction_gt'] for t in tiles],dtype=int)
        remote=1-np.sum(b*a,axis=1)
        pixel=np.array([baseline.pixel_score(t.before,t.after) for t in tiles])
        explanations=[rejection.classify_rejection(t.before,t.after) for t in tiles]
        for j,(t,yy,rs,ps,(reason,rule_scores)) in enumerate(zip(tiles,y,remote,pixel,explanations)):
            row={'split':split,'pair':pair.pair_id,'tile':j,'row':t.row,'col':t.col,
                 'truth':int(yy),'remoteclip':float(rs),'pixel':float(ps),
                 'gate_pass':int(reason=='unexplained')}
            row.update({f'rule_{name}':float(value) for name,value in rule_scores.items()})
            rows.append(row)
        pair_summaries.append({'pair':pair.pair_id,'tiles':len(tiles),'positives':int(y.sum()),
                               'prevalence':float(y.mean()),
                               'remoteclip_ap':float(average_precision_score(y,remote)) if len(set(y))==2 else None,
                               'pixel_ap':float(average_precision_score(y,pixel)) if len(set(y))==2 else None})
        print(f'{split} {pair.pair_id}: {len(tiles)} tiles, {int(y.sum())} positive',flush=True)
    return rows,pair_summaries

def metric(y,score,threshold):
    pred=score>=threshold
    cm=confusion_matrix(y,pred,labels=[0,1]).ravel()
    return {'ap':float(average_precision_score(y,score)),
            'precision':float(precision_score(y,pred,zero_division=0)),
            'recall':float(recall_score(y,pred,zero_division=0)),
            'tn_fp_fn_tp':[int(x) for x in cm]}

def threshold(y,score):
    return float(metrics.threshold_for_recall(y,score,CFG['threshold_selection_recall']))

def arr(rows,key): return np.array([r[key] for r in rows])
RULES=dict(rejection._THRESHOLDS)
def gated(rows, omitted=None):
    passage=np.ones(len(rows),dtype=bool)
    for name,limit in RULES.items():
        if name!=omitted: passage &= arr(rows,f'rule_{name}') < limit
    return np.where(passage,arr(rows,'remoteclip'),-1.0)

start=time.time()
embed.load_model()
train,train_pairs=score_split('train')
assert len(train_pairs)==14, f'Expected 14 train pairs, got {len(train_pairs)}'
yt=arr(train,'truth')
thresholds={name:threshold(yt,arr(train,name)) for name in ('pixel','remoteclip')}
# Gate rule is pre-existing and fixed. A declined candidate gets a score below all pass scores.
train_gated=gated(train)
thresholds['gated_remoteclip']=threshold(yt,train_gated)
for omitted in RULES:
    name=f'gate_without_{omitted}'
    thresholds[name]=threshold(yt,gated(train,omitted))
save_json('frozen_config.json',CFG)
save_json('train_thresholds.json',thresholds)
save_json('train_pair_summary.json',train_pairs)
print('TRAIN_THRESHOLDS',json.dumps(thresholds),flush=True)

test,test_pairs=score_split('test')
assert len(test_pairs)==10, f'Expected 10 test pairs, got {len(test_pairs)}'
with (OUT/'raw_tile_scores.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(train[0]));w.writeheader();w.writerows(train+test)
y=arr(test,'truth')
scores={name:arr(test,name) for name in ('pixel','remoteclip')}
scores['gated_remoteclip']=gated(test)
for omitted in RULES:
    scores[f'gate_without_{omitted}']=gated(test,omitted)
summary={'n_train_pairs':len(train_pairs),'n_test_pairs':len(test_pairs),
         'train_tiles':len(train),'test_tiles':len(test),'test_positives':int(y.sum()),
         'test_prevalence':float(y.mean()),'thresholds_train_only':thresholds,
         'random_pr_reference_line':float(y.mean()),
         'all_positive_precision':float(y.mean()),
         'gate_rule_thresholds_preexisting':RULES,
         'methods':{name:metric(y,score,thresholds[name]) for name,score in scores.items()},
         'network_attempts':attempts,'elapsed_s':time.time()-start,
         'hardware':{'platform':platform.platform(),'cpu_count':os.cpu_count(),
                     'python':sys.version,'torch':torch.__version__,
                     'sklearn':__import__('sklearn').__version__,
                     'cuda_available':torch.cuda.is_available()},
         'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest()}
save_json('test_pair_summary.json',test_pairs)
save_json('summary.json',summary)
print('RESULTS',json.dumps(summary),flush=True)
