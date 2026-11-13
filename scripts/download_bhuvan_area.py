"""Fetch a bounded public Bhuvan map layer; preserve service metadata."""
import urllib.request, pathlib, json, math, concurrent.futures, io, hashlib, datetime
from PIL import Image
import numpy as np
import rasterio
from rasterio.transform import from_origin
root=pathlib.Path('datasets/knowledge_park2_river_bhuvan'); root.mkdir(parents=True,exist_ok=True)
# URL template observed in Bhuvan's rendered map asset inventory.
base='https://bhuvanmaps.nrsc.gov.in/bhuvan_ras3/server/rest/services/World_Imagery/MapServer/WMTS'
z=16
west,south,east,north=77.46,28.435,77.515,28.483
def tile(lon,lat):
    return int((lon+180)/360*2**z),int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*2**z)
x0,y0=tile(west,north); x1,y1=tile(east,south)
tile_dir=root/'tiles_z16'; tile_dir.mkdir(exist_ok=True)
def fetch(pair):
    x,y=pair
    url=f'{base}?service=WMTS&version=1.0.0&request=GetTile&layer=HYDImagery&style=default&tilematrixSet=GoogleMapsCompatible&tilematrix={z}&tilerow={y}&tilecol={x}&format=image/jpeg'
    path=tile_dir/f'{z}_{x}_{y}.jpg'
    if not path.exists():
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://bhuvan.nrsc.gov.in/'})
        data=urllib.request.urlopen(req,timeout=50).read()
        im=Image.open(io.BytesIO(data)); im.verify(); path.write_bytes(data)
    im=Image.open(path).convert('RGB')
    if im.size!=(256,256): raise ValueError(f'Unexpected tile size {im.size}')
    return x,y,im,{'file':str(path),'url':url,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
pairs=[(x,y) for y in range(y0,y1+1) for x in range(x0,x1+1)]
print(f'Downloading {len(pairs)} tiles',flush=True)
canvas=Image.new('RGB',((x1-x0+1)*256,(y1-y0+1)*256)); records=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    for i,(x,y,im,record) in enumerate(pool.map(fetch,pairs),1):
        canvas.paste(im,((x-x0)*256,(y-y0)*256)); records.append(record)
        if i%10==0: print(f'{i}/{len(pairs)}',flush=True)
canvas.save(root/'knowledge_park2_river_interchange.png')
res=2*math.pi*6378137/(256*2**z); origin=math.pi*6378137
transform=from_origin(x0*256*res-origin,origin-y0*256*res,res,res)
with rasterio.open(root/'knowledge_park2_river_interchange.tif','w',driver='GTiff',width=canvas.width,height=canvas.height,count=3,dtype='uint8',crs='EPSG:3857',transform=transform,compress='deflate') as dst:
    dst.write(np.array(canvas).transpose(2,0,1))
meta={'source':'Bhuvan / NRSC public WMTS display imagery','retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'acquisition_date':None,'displayed_layer_label':'HRS:2018-19,2017 (map UI label; not verified per-pixel acquisition date)','requested_bbox_wgs84':[west,south,east,north],'zoom':z,'pixel_spacing_epsg3857_m':res,'georeferencing':'Derived from GoogleMapsCompatible WMTS grid, not original satellite product metadata','tiles':records}
(root/'provenance.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
print(f'Saved PNG and GeoTIFF {canvas.size}',flush=True)
