"""Exact chance P@5 for the provisional 56-chip Noida judgment pool.

This is a descriptive baseline for the historical probe, not new validation.
"""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
judgments=json.loads((ROOT/'reality_check/fresh_query_judgments.json').read_text(encoding='utf-8'))
old=json.loads((ROOT/'reality_check/results.json').read_text(encoding='utf-8'))
pool=56
queries=[]
for (query,ids),result in zip(judgments['queries'],old['fresh_retrieval']):
    assert query==result['query']
    assert all(0<=int(i)<pool for i in ids+result['top5_local_ids'])
    queries.append({'query':query,'relevant':len(ids),'pool':pool,
                    'random_expected_p_at_5':len(ids)/pool,
                    'observed_p_at_5':result['precision_at_5']})
images=[]
for result,(_,ids) in zip(old['fresh_image_retrieval'],judgments['queries']):
    qid=result['query_local_id']
    images.append({'query_local_id':qid,'relevant_excluding_self':len(ids)-(qid in ids),
                   'pool_excluding_self':pool-1,
                   'random_expected_p_at_5':(len(ids)-(qid in ids))/(pool-1),
                   'observed_p_at_5':result['precision_at_5']})
out={'caveat':'All 56 labels are provisional one-reviewer judgments; this assumes the area-filtered ranking pool is exactly these 56 chips.',
     'text_queries':queries,'image_queries':images,
     'text_mean_random_expected_p_at_5':sum(x['random_expected_p_at_5'] for x in queries)/len(queries),
     'text_mean_observed_p_at_5':sum(x['observed_p_at_5'] for x in queries)/len(queries),
     'image_mean_random_expected_p_at_5':sum(x['random_expected_p_at_5'] for x in images)/len(images),
     'image_mean_observed_p_at_5':sum(x['observed_p_at_5'] for x in images)/len(images)}
dest=ROOT/'results/retrieval_chance.json'
dest.write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
