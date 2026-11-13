"""Geometric recovery check on synthetic perturbations of OSCD training images."""
import csv,json,sys
from pathlib import Path
import cv2,numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
cfg=json.loads((ROOT/'configs/registration.json').read_text(encoding='utf-8'))
sys.path.insert(0,str(Path(r'C:\Users\abcom\Downloads\anveshan\src')))
sys.path.insert(0,str(ROOT))
from anveshan import oscd,config
from app.place_matching import local_features,verify_place
config.OSCD_DIR=Path(r'C:\Users\abcom\Downloads\anveshan\data\oscd')
out=ROOT/'results/registration'
out.mkdir(parents=True,exist_ok=True)
rows=[]
for pair in oscd.load_pairs(cfg['split']):
    img=np.asarray(pair.before.convert('RGB'))
    h,w=img.shape[:2]
    left=local_features(Image.fromarray(img))
    corners=np.float32([[0,0],[w,0],[w,h],[0,h]]).reshape(-1,1,2)
    for spec in cfg['transform_cases']:
        M=cv2.getRotationMatrix2D((w/2,h/2),spec['angle_deg'],spec['scale'])
        M[:,2]+=[spec['dx'],spec['dy']]
        moved=cv2.warpAffine(img,M,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        proof=verify_place(left,local_features(Image.fromarray(moved)))
        rmse=None
        if proof['matched']:
            expected=cv2.transform(corners,M).reshape(-1,2)
            recovered=cv2.perspectiveTransform(corners,np.asarray(proof['homography'],dtype='float64')).reshape(-1,2)
            rmse=float(np.sqrt(np.mean(np.sum((expected-recovered)**2,axis=1))))
        rows.append({'pair':pair.pair_id,'case':spec['name'],'matched':int(proof['matched']),
                     'corner_rmse_px':rmse,'inliers':proof.get('inliers'),
                     'inlier_fraction':proof.get('inlier_fraction'),
                     'coverage':proof.get('coverage'),'overlap':proof.get('overlap')})
    print(pair.pair_id,flush=True)
with (out/'raw.csv').open('w',newline='',encoding='utf-8') as f:
    wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
summary=[]
for case in [x['name'] for x in cfg['transform_cases']]:
    group=[r for r in rows if r['case']==case]
    errors=[r['corner_rmse_px'] for r in group if r['corner_rmse_px'] is not None]
    summary.append({'case':case,'n':len(group),'success':sum(r['matched'] for r in group),
                    'success_rate':sum(r['matched'] for r in group)/len(group),
                    'median_corner_rmse_px_success_only':float(np.median(errors)) if errors else None})
report={'protocol':cfg,'rows':summary,'limitation':'Synthetic same-date registration on training images; no test-pair change-screening comparison.'}
(out/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
