import argparse
import ctypes
import json
import os
from pathlib import Path
import sqlite3
import winreg

p=argparse.ArgumentParser()
p.add_argument('before',type=Path)
p.add_argument('after',type=Path)
a=p.parse_args()
class Memory(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('total','available','page','availpage','virtual','availvirtual','extended')]
m=Memory(); m.length=ctypes.sizeof(m)
ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as k:
    cpu=winreg.QueryValueEx(k,'ProcessorNameString')[0]
b=json.loads((a.before/'report.json').read_text()); c=json.loads((a.after/'report.json').read_text())
out={'cpu':cpu,'ram_gib':m.total/2**30,'logical_cpus':os.cpu_count(),
     'before_seconds':b['seconds'],'after_seconds':c['seconds'],
     'before_stages':b['stages'],'after_stages':c['stages'],
     'groups_identical':b['groups']==c['groups'],
     'similar_sites_identical':b['similar_sites']==c['similar_sites'],
     'counts_identical':b['counts']==c['counts'],
     'decisions_identical':all(b['status'].get(k)==c['status'].get(k) for k in ('accepted','excluded','duplicates','review','unmatched_scene_ids'))}
for table,cols,order in [('features','vector,positive,negative','substr(key, instr(key, ""))'),('scene_features','scene_id,vector','scene_id'),('tile_features','scene_id,tile_index,row,col,water_fraction,vector','scene_id,tile_index')]:
    with sqlite3.connect(a.before/'semantic_cache.sqlite3') as x, sqlite3.connect(a.after/'semantic_cache.sqlite3') as y:
        # Check feature rows by pixel digest; model file timestamps differ after install.
        if table=='features':
            cols='substr(key,-64),vector,positive,negative'; order='substr(key,-64)'
        left=x.execute(f'SELECT {cols} FROM {table} ORDER BY {order}').fetchall()
        right=y.execute(f'SELECT {cols} FROM {table} ORDER BY {order}').fetchall()
        out[table+'_identical']=left==right
print(json.dumps(out,indent=2))
