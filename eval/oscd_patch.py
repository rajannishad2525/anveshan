"""Patch-token change scoring on the frozen full-OSCD split. Run once.

Same data, tiles, labels, checkpoint and train-only threshold rule as
eval/oscd_full.py. The only change is how a tile pair is scored: instead of one
whole-tile embedding distance, compare the ViT patch tokens of the two dates
and aggregate the per-patch distances. "Centred" variants first subtract each
tile's mean token, so a shift that hits the whole tile (season, illumination)
cancels and only local change remains.

The variant is chosen by train AP alone; the test split is scored once.
No data/model downloads. Refuses to overwrite results/oscd_patch/.
"""
from __future__ import annotations
import hashlib, json, os, platform, socket, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / 'configs/oscd_full.json').read_text(encoding='utf-8'))
OUT = ROOT / 'results/oscd_patch'
if OUT.exists() and any(OUT.iterdir()):
    raise SystemExit(f'Refusing to overwrite frozen evaluation: {OUT}')
OUT.mkdir(parents=True, exist_ok=True)
os.environ['HF_HUB_OFFLINE'] = '1'
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
from anveshan import baseline, change, config, embed, metrics, oscd

TOP_SHARE = 0.10


def top_mean(d, share=TOP_SHARE):
    """Mean of the largest `share` of each row's patch distances."""
    k = max(1, int(round(d.shape[1] * share)))
    return np.sort(d, axis=1)[:, -k:].mean(1)

assert np.allclose(top_mean(np.arange(20.0).reshape(1, 20)), [18.5])  # top 2 of 20


def unit(t):
    return t / t.norm(dim=-1, keepdim=True).clamp_min(1e-6)


@torch.no_grad()
def encode(images, model, preprocess, batch_size):
    """Return (pooled, patch tokens) for PIL images; tokens are (n, 49, width)."""
    pooled, tokens = [], []
    for s in range(0, len(images), batch_size):
        x = torch.stack([preprocess(im.convert('RGB')) for im in images[s:s + batch_size]])
        p, t = model.visual(x)
        pooled.append(p); tokens.append(t)
    return torch.cat(pooled), torch.cat(tokens)


def pair_scores(before, after, model, preprocess):
    pb, tb = encode(before, model, preprocess, CFG['batch_size'])
    pa, ta = encode(after, model, preprocess, CFG['batch_size'])
    raw = (1 - (unit(tb) * unit(ta)).sum(-1)).numpy()
    cb, ca = tb - tb.mean(1, keepdim=True), ta - ta.mean(1, keepdim=True)
    cen = (1 - (unit(cb) * unit(ca)).sum(-1)).numpy()
    return {
        'whole_tile': (1 - (unit(pb) * unit(pa)).sum(-1)).numpy(),
        'patch_mean': raw.mean(1),
        'patch_max': raw.max(1),
        'patch_top10': top_mean(raw),
        'centred_mean': cen.mean(1),
        'centred_max': cen.max(1),
        'centred_top10': top_mean(cen),
    }


def score_split(split, model, preprocess):
    rows = []
    for pair in oscd.load_pairs(split):
        tiles = change.tile_pair(pair.before, pair.after, pair.mask, tile_size=CFG['tile_size_px'])
        if not tiles:
            raise RuntimeError(f'No complete tiles: {pair.pair_id}')
        sc = pair_scores([Image.fromarray(t.before) for t in tiles],
                         [Image.fromarray(t.after) for t in tiles], model, preprocess)
        for j, t in enumerate(tiles):
            row = {'split': split, 'pair': pair.pair_id, 'tile': j,
                   'truth': int(t.mask.mean() > CFG['positive_mask_fraction_gt']),
                   'pixel': float(baseline.pixel_score(t.before, t.after))}
            row.update({k: float(v[j]) for k, v in sc.items()})
            rows.append(row)
        print(f'{split} {pair.pair_id}: {len(tiles)} tiles', flush=True)
    return rows


def arr(rows, key):
    return np.array([r[key] for r in rows])


def metric(y, s, thr):
    pred = s >= thr
    return {'ap': float(average_precision_score(y, s)),
            'precision': float(precision_score(y, pred, zero_division=0)),
            'recall': float(recall_score(y, pred, zero_division=0)),
            'tn_fp_fn_tp': [int(x) for x in confusion_matrix(y, pred, labels=[0, 1]).ravel()]}


def pair_bootstrap(rows, key, n, seed):
    """95% AP interval resampling whole test pairs, not correlated tiles."""
    rng = np.random.default_rng(seed)
    pairs = sorted({r['pair'] for r in rows})
    by = {p: [r for r in rows if r['pair'] == p] for p in pairs}
    aps = []
    for _ in range(n):
        pick = [r for p in rng.choice(pairs, len(pairs)) for r in by[p]]
        y = arr(pick, 'truth')
        if 0 < y.sum() < len(y):
            aps.append(average_precision_score(y, arr(pick, key)))
    return [float(np.percentile(aps, 2.5)), float(np.percentile(aps, 97.5))]


start = time.time()
torch.set_num_threads(CFG['torch_threads'])
config.OSCD_DIR = Path(CFG['dataset_root'])
checkpoint = ROOT / CFG['checkpoint']
embed._checkpoint_path = lambda: str(checkpoint)
model, preprocess, _ = embed.load_model()
model.visual.output_tokens = True

train = score_split('train', model, preprocess)
yt = arr(train, 'truth')
VARIANTS = ['whole_tile', 'patch_mean', 'patch_max', 'patch_top10',
            'centred_mean', 'centred_max', 'centred_top10']
train_ap = {v: float(average_precision_score(yt, arr(train, v))) for v in VARIANTS + ['pixel']}
picked = max((v for v in VARIANTS if v != 'whole_tile'), key=train_ap.get)
thresholds = {k: float(metrics.threshold_for_recall(yt, arr(train, k), CFG['threshold_selection_recall']))
              for k in VARIANTS + ['pixel']}
(OUT / 'train_selection.json').write_text(json.dumps(
    {'train_ap': train_ap, 'picked_on_train': picked, 'thresholds_train_only': thresholds}, indent=2))
print('PICKED_ON_TRAIN', picked, json.dumps(train_ap), flush=True)

test = score_split('test', model, preprocess)
y = arr(test, 'truth')
rng = np.random.default_rng(CFG['seed'])
random_ap = float(np.mean([average_precision_score(y, rng.random(len(y))) for _ in range(CFG['random_rankings'])]))
summary = {
    'picked_on_train': picked,
    'test_tiles': len(test), 'test_positives': int(y.sum()), 'test_prevalence': float(y.mean()),
    'random_ap_mean': random_ap,
    'methods': {k: {**metric(y, arr(test, k), thresholds[k]),
                    'ap_ci95_pair_bootstrap': pair_bootstrap(test, k, CFG['bootstrap_resamples'], CFG['seed'])}
                for k in VARIANTS + ['pixel']},
    'per_pair_ap': {p: {k: float(average_precision_score(arr(rs, 'truth'), arr(rs, k)))
                        for k in ('pixel', 'whole_tile', picked)}
                    for p in sorted({r['pair'] for r in test})
                    for rs in [[r for r in test if r['pair'] == p]]
                    if 0 < arr(rs, 'truth').sum() < len(rs)},
    'network_attempts': attempts, 'elapsed_s': time.time() - start,
    'hardware': {'platform': platform.platform(), 'cpu_count': os.cpu_count(),
                 'torch': torch.__version__, 'cuda_available': torch.cuda.is_available()},
    'checkpoint_sha256': hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
}
import csv
with (OUT / 'raw_tile_scores.csv').open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(train[0])); w.writeheader(); w.writerows(train + test)
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print('RESULTS', json.dumps({k: round(v['ap'], 4) for k, v in summary['methods'].items()}), flush=True)
