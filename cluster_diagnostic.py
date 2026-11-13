import sqlite3, torch, numpy as np, json
from app.semantic_clusters import ClusterEngine, POSITIVE,NEGATIVE
from app.main import ROOT,conn
from PIL import Image,ImageDraw
engine=ClusterEngine(ROOT,conn);engine.load()
c=sqlite3.connect('datasets/semantic_cache.sqlite3'); rows=c.execute('select vector from features limit 3').fetchall()
for (v,) in rows:
 scores=engine.text@np.frombuffer(v,dtype='float32');print(sorted(zip(POSITIVE+NEGATIVE,scores.tolist()),key=lambda x:-x[1])[:7],flush=True)
# Artificial non-satellite logo fixtures only, never added to the user archive.
for bg,fg in [('white','navy'),('black','white')]:
 im=Image.new('RGB',(256,256),bg);d=ImageDraw.Draw(im);d.ellipse((40,30,216,206),outline=fg,width=15);d.text((80,115),'ACME LOGO',fill=fg)
 with torch.inference_mode():
  v=engine.model.encode_image(engine.preprocess(im).unsqueeze(0));v=(v/v.norm(dim=-1,keepdim=True)).numpy()[0]
 scores=engine.text@v;print('LOGO',sorted(zip(POSITIVE+NEGATIVE,scores.tolist()),key=lambda x:-x[1])[:5],flush=True)
