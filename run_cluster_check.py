import time,json
from app.main import cluster_engine
cluster_engine.ensure()
while cluster_engine.running: time.sleep(2)
s=cluster_engine.status
print({k:v for k,v in s.items() if k!='review'},flush=True)
print([(g['count'],g['minimum_similarity']) for g in cluster_engine.groups],flush=True)
open('datasets/clustering_reality_check.json','w').write(json.dumps({'status':s,'groups':cluster_engine.groups},indent=2))
