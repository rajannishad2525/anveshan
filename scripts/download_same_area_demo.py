"""Download public Sentinel-2 crops without modifying the active archive."""
import json
import hashlib
import urllib.request
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from PIL import Image, ImageDraw

class RemoteFile(io.RawIOBase):
    """Bounded HTTP ranges with retries for unreliable long transfers."""
    def __init__(self, url):
        print('Opening range source',url,flush=True)
        self.url=url; self.pos=0; self.cache={}
        req=urllib.request.Request(url,headers={'Range':'bytes=0-0'})
        with urllib.request.urlopen(req,timeout=30) as r:
            self.size=int(r.headers['Content-Range'].split('/')[-1]); r.read()
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self, offset, whence=0):
        self.pos=offset if whence==0 else (self.pos+offset if whence==1 else self.size+offset)
        return self.pos
    def read(self,n=-1):
        if n<0: n=self.size-self.pos
        end=min(self.size,self.pos+n); parts=[]; block=262144
        def fetch(start):
            stop=min(start+block,self.size)-1
            for attempt in range(3):
                try:
                    req=urllib.request.Request(self.url,headers={'Range':f'bytes={start}-{stop}'})
                    with urllib.request.urlopen(req,timeout=45) as r: data=r.read()
                    if len(data)!=stop-start+1: raise IOError('Incomplete range')
                    return start,data
                except Exception:
                    if attempt==2: raise
        missing=[start for start in range((self.pos//block)*block,end,block) if start not in self.cache]
        if missing:
            with ThreadPoolExecutor(max_workers=8) as pool:
                self.cache.update(pool.map(fetch,missing))
        while self.pos<end:
            start=(self.pos//block)*block
            if start not in self.cache:
                print('Range',start,flush=True)
                stop=min(start+block,self.size)-1
                for attempt in range(3):
                    try:
                        req=urllib.request.Request(self.url,headers={'Range':f'bytes={start}-{stop}'})
                        with urllib.request.urlopen(req,timeout=45) as r: data=r.read()
                        if len(data)!=stop-start+1: raise IOError('Incomplete range')
                        self.cache[start]=data;break
                    except Exception:
                        if attempt==2: raise
            amount=min(end-self.pos,start+block-self.pos)
            parts.append(self.cache[start][self.pos-start:self.pos-start+amount]);self.pos+=amount
        return b''.join(parts)

OUT = Path(__file__).resolve().parents[1] / 'demo_data' / 'same_location_false_alarm'
OUT.mkdir(parents=True, exist_ok=True)
BBOX = [77.46, 28.435, 77.515, 28.483]
url = ('https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items'
       '?limit=100&bbox=77.46,28.435,77.515,28.483'
       '&datetime=2024-01-01T00:00:00Z/2024-12-31T23:59:59Z')
catalog = json.load(urllib.request.urlopen(url, timeout=45))
(OUT/'catalog.json').write_text(json.dumps(catalog), encoding='utf-8')
items = catalog['features']
def month(i): return int(i['properties']['datetime'][5:7])
chosen=[]
for label, months, cloudy in [('winter_clear',[1,2],False),('summer_clear',[4,5],False),('monsoon_clear_candidate',[7,8,9],False),('autumn_clear',[10,11],False),('cloud_candidate',[7,8],True),('winter_cloud_candidate',[1,2,12],True)]:
    candidates=[i for i in items if month(i) in months and i['id'] not in [x[1]['id'] for x in chosen]]
    chosen.append((label, sorted(candidates,key=lambda i:i['properties']['eo:cloud_cover'], reverse=cloudy)[0]))
records=[]
previews=[]
with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif', GDAL_HTTP_TIMEOUT='45'):
    for label,item in chosen:
        date=item['properties']['datetime'][:10]
        stem=f'{date}_{label}'
        print('Downloading',stem,flush=True)
        record={'label':label,'date':date,'item_id':item['id'],'bbox_wgs84':BBOX,'assets':{},'scene_cloud_percent':item['properties']['eo:cloud_cover']}
        for key in ['visual','scl']:
            asset=item['assets'][key]['href']
            dest=OUT/f'{stem}_{key}.tif'
            if not dest.exists():
                with rasterio.open(asset, opener=lambda path, mode='r': RemoteFile(path) if str(path).startswith('https:') else io.BytesIO()) as src:
                    bounds=transform_bounds('EPSG:4326',src.crs,*BBOX)
                    win=from_bounds(*bounds,src.transform).round_offsets().round_lengths()
                    arr=src.read(window=win)
                    profile=src.profile.copy()
                    profile.update(width=arr.shape[2],height=arr.shape[1],transform=src.window_transform(win),driver='GTiff',compress='deflate')
                    with rasterio.open(dest,'w',**profile) as dst: dst.write(arr)
            with rasterio.open(dest) as src: arr=src.read()
            record['assets'][key]={'file':dest.name,'source':asset,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}
            if key=='visual':
                im=Image.fromarray(np.moveaxis(arr[:3],0,-1))
                im.save(OUT/f'{stem}.png')
                im.thumbnail((360,340))
                tile=Image.new('RGB',(380,400),'#101c18');tile.paste(im,(10,35))
                ImageDraw.Draw(tile).text((10,10),stem,fill='white');previews.append(tile)
            else:
                vals=arr[0]; valid=vals!=0
                record['local_scl_cloud_percent']=round(float(np.isin(vals,[8,9,10])[valid].mean()*100),2) if valid.any() else None
                record['local_scl_shadow_percent']=round(float((vals[valid]==3).mean()*100),2) if valid.any() else None
        records.append(record)
        (OUT/'manifest.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
sheet=Image.new('RGB',(1140,800),'#101c18')
for n,im in enumerate(previews):sheet.paste(im,((n%3)*380,(n//3)*400))
sheet.save(OUT/'contact_sheet.jpg')
(OUT/'README.md').write_text('''# Same-location false-alarm test imagery
Area: Knowledge Park II / river-interchange, Greater Noida, matching the existing Bhuvan project area.
Source: Copernicus Sentinel-2 L2A via Element84 Earth Search public catalog.
Six real acquisition dates. RGB visual GeoTIFFs and PNG previews; SCL files are classification masks, NOT imagery to import.
RGB resolution is 10 m, lower than the existing Bhuvan display imagery. All crops cover the same requested area.
Use *_visual.tif for imports. Do not import contact_sheet.jpg or *_scl.tif as scenes.
Cloud/shadow percentages in manifest are local SCL classifications, not hand-validated truth.
Seasonal pairs are candidates; actual land changes can coexist. These images do not establish a no-change ground truth or model accuracy.
Original active archive and clusters were not modified. Source URLs, dates, and SHA-256 hashes are in manifest.json.
''',encoding='utf-8')
print(json.dumps(records,indent=2),flush=True)
