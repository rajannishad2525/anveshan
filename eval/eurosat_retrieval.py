"""Retrieval on 16,200 human-labelled EuroSAT RGB patches. Run once.

Replaces the 3-query Noida probe with labels nobody on the team wrote.
Text queries use one fixed prompt per class, written before any scoring and
never tuned. Image queries are a seeded sample of patches per class, each
ranked against all other patches. The chance baseline is class prevalence.

No data/model downloads. Refuses to overwrite results/eurosat_retrieval/.
"""
from __future__ import annotations
import hashlib, io, json, os, platform, socket, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / 'configs/oscd_full.json').read_text(encoding='utf-8'))
OUT = ROOT / 'results/eurosat_retrieval'
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
import pandas as pd
import torch
from PIL import Image
from sklearn.metrics import average_precision_score
PROJECT = Path(r'C:\Users\abcom\Downloads\anveshan')
sys.path.insert(0, str(PROJECT / 'src'))
from anveshan import embed

PARQUET = PROJECT / 'data/eurosat.parquet'
# Fixed before scoring; one plain phrase per EuroSAT class, label order 0..9.
PHRASES = ['annual crop fields', 'a forest', 'herbaceous vegetation', 'a highway',
           'industrial buildings', 'a pasture', 'permanent crop plantations',
           'residential buildings', 'a river', 'a sea or lake']
PROMPT = 'a satellite image of {}'
IMAGE_QUERIES_PER_CLASS = 50


def precision_at(rel_sorted, k):
    return float(rel_sorted[:k].mean())

assert precision_at(np.array([1, 0, 1, 1]), 2) == 0.5


start = time.time()
torch.set_num_threads(CFG['torch_threads'])
checkpoint = ROOT / CFG['checkpoint']
embed._checkpoint_path = lambda: str(checkpoint)
embed.load_model()

frame = pd.read_parquet(PARQUET)
labels = frame['label'].to_numpy()
images = [Image.open(io.BytesIO(b['bytes'])).convert('RGB') for b in frame['image']]
print(f'{len(images)} patches, embedding...', flush=True)
V = embed.embed_images(images, batch_size=64)
T = embed.embed_text([PROMPT.format(p) for p in PHRASES])

text = {}
for c, phrase in enumerate(PHRASES):
    rel = (labels == c).astype(int)
    s = V @ T[c]
    order = np.argsort(-s)
    text[phrase] = {'ap': float(average_precision_score(rel, s)), 'prevalence': float(rel.mean()),
                    'p@10': precision_at(rel[order], 10), 'p@50': precision_at(rel[order], 50)}

rng = np.random.default_rng(CFG['seed'])
image = {}
for c, phrase in enumerate(PHRASES):
    picks = rng.choice(np.flatnonzero(labels == c), IMAGE_QUERIES_PER_CLASS, replace=False)
    aps, p10 = [], []
    for q in picks:
        keep = np.arange(len(labels)) != q
        rel = (labels[keep] == c).astype(int)
        s = V[keep] @ V[q]
        aps.append(average_precision_score(rel, s))
        p10.append(precision_at(rel[np.argsort(-s)], 10))
    image[phrase] = {'map': float(np.mean(aps)), 'p@10': float(np.mean(p10)),
                     'prevalence': float((labels == c).mean())}

def macro(d, k):
    return float(np.mean([v[k] for v in d.values()]))

summary = {
    'patches': len(labels), 'classes': len(PHRASES), 'prompt': PROMPT,
    'text': {'per_class': text, 'mAP': macro(text, 'ap'), 'mean_p@10': macro(text, 'p@10'),
             'chance_mAP': macro(text, 'prevalence')},
    'image': {'queries_per_class': IMAGE_QUERIES_PER_CLASS, 'per_class': image,
              'mAP': macro(image, 'map'), 'mean_p@10': macro(image, 'p@10'),
              'chance_mAP': macro(image, 'prevalence')},
    'network_attempts': attempts, 'elapsed_s': time.time() - start,
    'hardware': {'platform': platform.platform(), 'cpu_count': os.cpu_count(),
                 'torch': torch.__version__, 'cuda_available': torch.cuda.is_available()},
    'checkpoint_sha256': hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
    'data_sha256': hashlib.sha256(PARQUET.read_bytes()).hexdigest(),
}
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print('RESULTS', json.dumps({m: {k: round(summary[m][k], 3) for k in ('mAP', 'mean_p@10', 'chance_mAP')}
                             for m in ('text', 'image')}), flush=True)
