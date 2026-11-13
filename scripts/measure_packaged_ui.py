"""Cold index benchmark through the shipped WebView2 BUILD LOCAL INDEX button.

Uses a private SQLite backup and ephemeral loopback server, never the live cache.
Run with the installed runtime/python.exe. The visible test window closes after
recording READY or an error. No screenshots or UI state are fabricated.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time
import urllib.request

p=argparse.ArgumentParser()
p.add_argument('--package',type=Path,required=True)
p.add_argument('--archive',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args(); a.output=a.output.resolve(); a.output.mkdir(parents=True,exist_ok=False)
os.environ['ANVESHAN_DATA_DIR']=str(a.output)
os.environ['CUDA_VISIBLE_DEVICES']=''
os.environ['HF_HUB_OFFLINE']='1'
sys.path.insert(0,str(a.package))
with sqlite3.connect((a.archive/'library.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(a.output/'library.sqlite3') as dst:
    src.backup(dst)
import desktop
import app.main as main
import uvicorn
import webview
port=desktop.free_port(); url=f'http://127.0.0.1:{port}'
server=uvicorn.Server(uvicorn.Config(main.app,host='127.0.0.1',port=port,log_level='error'))
threading.Thread(target=server.run,daemon=True).start()
assert desktop.wait_until_serving(url)
window=webview.create_window('ANVESHAN — packaged cold-build verification',url,width=1280,height=900)
def exercise():
    samples=[]
    try:
        for _ in range(120):
            if window.evaluate_js('Boolean(document.querySelector("#clusterBuildIndex, #indexBuildBtn"))'):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError('Packaged BUILD LOCAL INDEX button did not appear')
        window.evaluate_js('document.getElementById("clusterNav")?.click()')
        start=time.perf_counter()
        window.evaluate_js('document.querySelector("#clusterBuildIndex, #indexBuildBtn").click()')
        for _ in range(1200):
            time.sleep(0.5)
            with urllib.request.urlopen(url+'/api/clusters/status',timeout=10) as r:
                status=json.load(r)
            sample={'seconds':time.perf_counter()-start,'status':status,
                    'ui':window.evaluate_js('document.getElementById("clusterList").innerText')}
            if not samples or status.get('state')!=samples[-1]['status'].get('state'):
                samples.append(sample)
            if status.get('state') in ('ready','error'):
                break
        if status.get('state')!='ready':
            raise RuntimeError(str(status))
        result={'seconds':time.perf_counter()-start,'status':status,'samples':samples,
                'module':main.__file__,'executable':sys.executable}
        (a.output/'ui-report.json').write_text(json.dumps(result,indent=2))
        with sqlite3.connect(a.output/'semantic_cache.sqlite3') as c:
            counts={t:c.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('features','scene_features','tile_features')}
        (a.output/'report.json').write_text(json.dumps({
            'seconds':result['seconds'],'status':status,'stages':status.get('stage_seconds',{}),
            'counts':counts,'groups':main.cluster_engine.groups,
            'similar_sites':main.cluster_engine.similar_sites,
        },indent=2))
        print(json.dumps({'seconds':result['seconds'],'module':main.__file__,'status':status}),flush=True)
    except Exception as exc:
        (a.output/'error.txt').write_text(repr(exc))
        print(repr(exc),flush=True)
    finally:
        window.destroy()
        server.should_exit=True
webview.start(exercise)
if (a.output/'error.txt').exists():
    raise SystemExit(1)
