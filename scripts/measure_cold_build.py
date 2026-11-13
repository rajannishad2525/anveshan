"""Isolated cold-cache benchmark using the installed embeddable interpreter.

Original archive is read through SQLite backup; no live cache is modified.
Run once per empty output directory. --code selects the code under test.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

p = argparse.ArgumentParser()
p.add_argument('--code', type=Path, required=True)
p.add_argument('--package', type=Path, required=True)
p.add_argument('--archive', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
args = p.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
os.environ['ANVESHAN_DATA_DIR'] = str(args.output)
os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['HF_HUB_OFFLINE'] = '1'
sys.path.insert(0, str(args.code))
with sqlite3.connect((args.archive / 'library.sqlite3').resolve().as_uri() + '?mode=ro', uri=True) as source:
    with sqlite3.connect(args.output / 'library.sqlite3') as dest:
        source.backup(dest)
def connect():
    c = sqlite3.connect(args.output / 'library.sqlite3')
    c.row_factory = sqlite3.Row
    return c
started = time.perf_counter()
from app.semantic_clusters import ClusterEngine
engine = ClusterEngine(args.package, connect)
rows = engine.snapshot()
timings = {}
def timed(obj, name):
    original = getattr(obj, name)
    def wrapped(*a, **kw):
        t = time.perf_counter()
        try:
            return original(*a, **kw)
        finally:
            timings[name] = timings.get(name, 0) + time.perf_counter() - t
    setattr(obj, name, wrapped)
timed(engine, 'load')
timed(engine, 'build_tile_features')
import app.semantic_clusters as module
timed(module, 'group_places')
engine.run(rows)
elapsed = time.perf_counter() - started
with sqlite3.connect(args.output / 'semantic_cache.sqlite3') as c:
    counts = {}
    hashes = {}
    for table, order in [('features', 'key'), ('scene_features', 'scene_id'), ('tile_features', 'scene_id,tile_index')]:
        values = c.execute(f'SELECT * FROM {table} ORDER BY {order}').fetchall()
        counts[table] = len(values)
        h = hashlib.sha256()
        for row in values:
            for v in row:
                h.update(v if isinstance(v, bytes) else repr(v).encode())
        hashes[table] = h.hexdigest()
report = dict(seconds=elapsed, stages=timings, status=engine.status,
              scenes=len(rows), bytes=sum(Path(r['path']).stat().st_size for r in rows),
              counts=counts, hashes=hashes, executable=sys.executable,
              code=str(args.code), groups=engine.groups, similar_sites=engine.similar_sites)
(args.output / 'report.json').write_text(json.dumps(report, indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('groups','similar_sites')}, indent=2), flush=True)
