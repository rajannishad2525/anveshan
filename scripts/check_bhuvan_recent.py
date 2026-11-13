import urllib.request,urllib.parse,io,pathlib,json
from PIL import Image
import numpy as np
root=pathlib.Path('datasets/knowledge_park2_river_bhuvan/tiles_z16/docx_temporal/recent_checks');root.mkdir(exist_ok=True)
records=[]
for layer in ['hrs_25rw','hrs_c2sw_26']:
    params={'styles':'','bbox':'8626683.012264993,3306971.5917298645,8626988.760378134,3307277.339843005','format':'image/png','service':'WMS','version':'1.1.1','request':'GetMap','srs':'EPSG:3857','transparent':'true','width':256,'height':256,'layers':layer}
    url='https://bhuvan-ras1.nrsc.gov.in/tilecache/tilecache.py??'+urllib.parse.urlencode(params)
    raw=urllib.request.urlopen(url,timeout=40).read();(root/f'{layer}_z17.png').write_bytes(raw)
    im=np.array(Image.open(io.BytesIO(raw)).convert('RGBA'))
    records.append({'layer':layer,'url':url,'visible_fraction':float((im[:,:,3]>0).mean()),'std':float(im[:,:,:3].std())})
(root/'checks.json').write_text(json.dumps(records,indent=2));print(json.dumps(records))
