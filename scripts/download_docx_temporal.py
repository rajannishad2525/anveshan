"""Build geospatial location catalogue and fetch observed Bhuvan historical WMS layers."""
import pathlib,zipfile,xml.etree.ElementTree as ET,re,json,math,csv,urllib.request,urllib.parse,concurrent.futures,io,hashlib,datetime
from PIL import Image
import numpy as np
import rasterio
from rasterio.transform import from_origin
ROOT=pathlib.Path('datasets/knowledge_park2_river_bhuvan/tiles_z16/docx_temporal')
ROOT.mkdir(parents=True,exist_ok=True)
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
with zipfile.ZipFile('_inspect_locations_report.docx') as z:
    doc=ET.fromstring(z.read('word/document.xml'))
    rels={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('word/_rels/document.xml.rels'))}
locations=[]; current=None
for p in doc.findall('.//w:p',ns):
    txt=''.join(p.itertext()).strip()
    m=re.fullmatch(r'(\d+\.\d+)\s*,\s*(\d+\.\d+)',txt)
    if m:
        current={'id':f'location_{len(locations)+1:03d}','latitude':float(m[1]),'longitude':float(m[2]),'address':'','docx_images':[]}
        locations.append(current)
    elif current:
        if txt and 'District,Uttar' not in txt: current['address']+=txt
        for b in p.findall('.//a:blip',ns):
            rid=b.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
            if rid in rels: current['docx_images'].append(rels[rid])
Z=16; RES=2*math.pi*6378137/(256*2**Z); ORIGIN=math.pi*6378137
for loc in locations:
    lon,lat=loc['longitude'],loc['latitude']
    loc['tile_x']=int((lon+180)/360*2**Z)
    loc['tile_y']=int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*2**Z)
(ROOT/'locations.json').write_text(json.dumps(locations,indent=2),encoding='utf-8')
features=[{'type':'Feature','geometry':{'type':'Point','coordinates':[l['longitude'],l['latitude']]},'properties':l} for l in locations]
(ROOT/'locations.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},indent=2),encoding='utf-8')
if not (ROOT/'layers.json').exists():
    print(json.dumps({'entries':len(locations),'unique_coordinates':len({(l['latitude'],l['longitude']) for l in locations}),'unique_tiles':len({(l['tile_x'],l['tile_y']) for l in locations}),'images':sum(len(l['docx_images']) for l in locations)})); raise SystemExit
layers=json.loads((ROOT/'layers.json').read_text())
tiles=sorted({(l['tile_x'],l['tile_y']) for l in locations})
def fetch(task):
    layer,x,y=task; folder=ROOT/layer['period']; folder.mkdir(exist_ok=True)
    file=folder/f'z16_{x}_{y}.png'
    left=x*256*RES-ORIGIN; top=ORIGIN-y*256*RES
    bbox=[left,top-256*RES,left+256*RES,top]
    args=dict(styles='',bbox=','.join(map(str,bbox)),format='image/png',service='WMS',version='1.1.1',request='GetMap',srs='EPSG:3857',transparent='true',width=256,height=256,layers=layer['layer'])
    url=layer['endpoint'].rstrip('?')+'?'+urllib.parse.urlencode(args)
    record=dict(period=layer['period'],tile_x=x,tile_y=y,url=url,file=str(file),bbox_epsg3857=bbox,acquisition_date=None)
    try:
        if not file.exists():
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://bhuvan.nrsc.gov.in/'})
            raw=urllib.request.urlopen(req,timeout=45).read()
            im=Image.open(io.BytesIO(raw)); im.load()
            if im.size!=(256,256): raise ValueError(f'Unexpected size: {im.size}')
            file.write_bytes(raw)
        im=Image.open(file).convert('RGBA'); arr=np.array(im)
        record['visible_fraction']=float((arr[:,:,3]>0).mean())
        record['rgb_std']=float(arr[:,:,:3].std())
        record['status']='ok' if record['visible_fraction']>.95 and record['rgb_std']>2 else 'no_data_or_partial'
        record['sha256']=hashlib.sha256(file.read_bytes()).hexdigest()
        record['pixel_sha256']=hashlib.sha256(arr.tobytes()).hexdigest()
        if record['status']=='ok':
            with rasterio.open(file.with_suffix('.tif'),'w',driver='GTiff',width=256,height=256,count=4,dtype='uint8',crs='EPSG:3857',transform=from_origin(left,top,RES,RES),compress='deflate') as dst: dst.write(arr.transpose(2,0,1))
    except Exception as exc: record.update(status='failed',error=str(exc))
    return record
tasks=[(layer,x,y) for layer in layers for x,y in tiles]
print(f'{len(locations)} location entries, {len(tiles)} unique z16 tiles, {len(tasks)} requests',flush=True)
records=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    for i,rec in enumerate(pool.map(fetch,tasks),1):
        records.append(rec)
        (ROOT/'download_manifest.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
        if i%10==0: print(f'{i}/{len(tasks)} {rec["period"]} {rec["status"]}',flush=True)
mapping=[]
for loc in locations:
    for rec in records:
        if (loc['tile_x'],loc['tile_y'])==(rec['tile_x'],rec['tile_y']): mapping.append({**{k:v for k,v in loc.items() if k!='docx_images'},'period':rec['period'],'file':rec['file'],'status':rec['status']})
with (ROOT/'location_period_index.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=list(mapping[0])); w.writeheader(); w.writerows(mapping)
summary={p:{s:sum(r['period']==p and r['status']==s for r in records) for s in ['ok','no_data_or_partial','failed']} for p in [l['period'] for l in layers]}
(ROOT/'summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary),flush=True)
