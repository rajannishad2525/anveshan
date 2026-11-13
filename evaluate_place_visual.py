import json,sqlite3,hashlib,re,time
import numpy as np
from app.semantic_clusters import read_rgb,compatible_footprints
from app.place_matching import local_features,group_places
start=time.perf_counter(); report=json.load(open('datasets/clustering_reality_check.json')); scenes=sorted([s for g in report['groups'] for s in g['scenes']],key=lambda s:s['id']);c=sqlite3.connect('datasets/semantic_cache.sqlite3');vectors=[];features=[]
for s in scenes:
 im=read_rgb(s['path']);digest=hashlib.sha256(str(im.size).encode()+im.tobytes()).hexdigest();v=c.execute('select vector from features where key like ? order by rowid desc limit 1',('%'+digest,)).fetchone()[0];vectors.append(np.frombuffer(v,dtype='float32'));features.append(local_features(im))
groups,singles,edges=group_places(scenes,vectors,features,compatible_footprints,use_geometry=False)
# Filename tile IDs used ONLY as a fixture reference, never passed to matching.
labels=[re.search(r'z\d+_\d+_\d+',s['name']).group() for s in scenes]
pred={(min(a,b),max(a,b)) for g in groups for a in g for b in g if a<b};truth={(a,b) for a in range(len(scenes)) for b in range(a+1,len(scenes)) if labels[a]==labels[b]};tp=len(pred&truth)
out={'mode':'visual only; coordinates disabled','images':len(scenes),'groups':[[scenes[i]['id'] for i in g] for g in groups],'singles':[scenes[i]['id'] for i in singles],'true_pairs':len(truth),'predicted_pairs':len(pred),'correct_pairs':tp,'pair_precision':tp/len(pred) if pred else None,'pair_recall':tp/len(truth),'elapsed_seconds':time.perf_counter()-start,'label_caveat':'existing tile IDs are weak fixture labels, not independently verified or held out','edges':[(scenes[a]['id'],scenes[b]['id'],e) for a,b,e in edges]};json.dump(out,open('datasets/place_visual_only_evaluation.json','w'),indent=2);print(json.dumps({k:v for k,v in out.items() if k!='edges'}),flush=True)
