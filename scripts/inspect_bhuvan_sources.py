import urllib.request, re, pathlib, concurrent.futures
root=pathlib.Path('datasets/bhuvan_source_check'); root.mkdir(parents=True,exist_ok=True)
base='https://bhuvan.nrsc.gov.in'
html=urllib.request.urlopen(base+'/ngmaps/',timeout=40).read().decode()
paths=set(re.findall(r'<script src="([^"]+)"',html))
def fetch(p):
    try:
        data=urllib.request.urlopen(base+p,timeout=40).read().decode()
        (root/pathlib.Path(p).name).write_text(data,encoding='utf-8')
        hits=[]
        for match in re.finditer(r'.{0,120}(?:wms|wmts|HRS|bhuvan-ras|Satellite|satellite|2025|2026).{0,240}',data,re.I):
            hits.append(match.group())
        return pathlib.Path(p).name, hits[:70]
    except Exception as e: return p,[str(e)]
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    for name,hits in pool.map(fetch,paths):
        if hits: print(name, '\n'.join(hits),sep='\n')
