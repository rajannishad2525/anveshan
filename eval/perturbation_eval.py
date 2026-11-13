"""Train-image synthetic controls for RemoteCLIP change-screen false alarms."""
import csv,json,os,socket,sys
from pathlib import Path
import numpy as np,torch
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
cfg=json.loads((ROOT/'configs/perturbation.json').read_text(encoding='utf-8'))
thresholds=json.loads((ROOT/cfg['screening_threshold_source']).read_text(encoding='utf-8'))
threshold=float(thresholds['remoteclip'])
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
def denied(*a,**kw):raise RuntimeError('Network disabled')
socket.socket.connect=denied;socket.create_connection=denied
sys.path.insert(0,str(Path(r'C:\Users\abcom\Downloads\anveshan\src')))
from anveshan import change,config,embed,oscd
config.OSCD_DIR=Path(r'C:\Users\abcom\Downloads\anveshan\data\oscd')
embed._checkpoint_path=lambda:str(ROOT/'models/RemoteCLIP-ViT-B-32.pt')
torch.set_num_threads(4);torch.set_num_interop_threads(1)
rng=np.random.default_rng(cfg['seed'])
all_tiles=[]
for pair in oscd.load_pairs(cfg['source_split']):
    for j,tile in enumerate(change.tile_pair(pair.before,pair.after,pair.mask,tile_size=cfg['tile_size_px'])):
        all_tiles.append((pair.pair_id,j,tile.before))
selection=rng.choice(len(all_tiles),size=cfg['n_chips'],replace=False)
picked=[all_tiles[int(i)] for i in selection]
original=np.array([x[2] for x in picked],dtype=np.uint8)
variants={
    'identical':original.copy(),
    'brightness':np.clip(original.astype(float)*cfg['brightness_multiplier'],0,255).astype('uint8'),
    'haze':np.clip(original.astype(float)*cfg['haze_multiplier']+cfg['haze_offset'],0,255).astype('uint8'),
    'seasonal_colour_proxy':np.clip(original.astype(float)*np.array(cfg['seasonal_rgb_multiplier']),0,255).astype('uint8'),
    'registration_shift':np.roll(original,cfg['shift_pixels'],axis=2),
}
embed.load_model()
base=embed.embed_images([Image.fromarray(x) for x in original],batch_size=16)
rows=[]
for name,arr in variants.items():
    vec=embed.embed_images([Image.fromarray(x) for x in arr],batch_size=16)
    dist=1-np.sum(base*vec,axis=1)
    for (pair,j,_),value in zip(picked,dist):
        rows.append({'pair':pair,'tile':j,'perturbation':name,'score':float(value),
                     'threshold':threshold,'flagged':int(value>=threshold)})
    print(name,int((dist>=threshold).sum()),'/',len(dist),flush=True)
out=ROOT/'results/perturbation';out.mkdir(parents=True,exist_ok=True)
with (out/'raw.csv').open('w',newline='',encoding='utf-8') as f:
    wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
summary={'config':cfg,'threshold_train_only':threshold,'cases':[
    {'perturbation':name,'n':cfg['n_chips'],'flagged':sum(x['flagged'] for x in rows if x['perturbation']==name),
     'flagged_rate':sum(x['flagged'] for x in rows if x['perturbation']==name)/cfg['n_chips']}
    for name in variants],
    'limitation':'Synthetic transformations of training imagery, not independent real-cloud/season labels or onset evaluation.'}
(out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
