import pathlib,json,html,collections,hashlib
R=pathlib.Path('datasets/knowledge_park2_river_bhuvan/tiles_z16/docx_temporal')
locs=json.loads((R/'locations.json').read_text()); recs=json.loads((R/'download_manifest.json').read_text())
valid=[r for r in recs if r['status']=='ok']; periods=list(dict.fromkeys(r['period'] for r in valid))
bytile=collections.defaultdict(list)
for l in locs: bytile[(l['tile_x'],l['tile_y'])].append(l)
duplicates=[]
for tile in bytile:
    group=[r for r in valid if (r['tile_x'],r['tile_y'])==tile]
    for i,a in enumerate(group):
        for b in group[i+1:]:
            if a['pixel_sha256']==b['pixel_sha256']: duplicates.append({'tile':tile,'periods':[a['period'],b['period']]})
(R/'identical_period_tiles.json').write_text(json.dumps(duplicates,indent=2))
def rel(path):return pathlib.Path(path).relative_to(R).as_posix()
rows=[]
for (x,y),ls in bytile.items():
    cells=''.join(f'<td><a href="{rel(r["file"])}"><img loading="lazy" src="{rel(r["file"])}" width="256" height="256"></a><br><a href="{rel(r["file"]).replace(".png",".tif")}">GeoTIFF</a></td>' for p in periods for r in valid if r['period']==p and r['tile_x']==x and r['tile_y']==y)
    labels=''.join(f'<p><b>{l["id"]}</b> — {html.escape(l["address"])}<br>{l["latitude"]}, {l["longitude"]}</p>' for l in ls)
    rows.append(f'<section id="tile-{x}-{y}"><h2>Tile {x}, {y}</h2><details><summary>{len(ls)} DOCX location entries in this tile</summary>{labels}</details><div class="scroll"><table><tr>'+''.join(f'<th>{p}</th>' for p in periods)+f'</tr><tr>{cells}</tr></table></div></section>')
options=''.join(f'<option value="tile-{l["tile_x"]}-{l["tile_y"]}">{l["id"]} — {html.escape(l["address"])}</option>' for l in locs)
page='''<!doctype html><meta charset="utf-8"><title>DOCX locations — Bhuvan historical imagery</title><style>body{font:16px system-ui;background:#101b21;color:#ecf0e8;margin:25px}a{color:#a7d7ed}section{border-top:1px solid #456;padding:15px 0}th{padding:10px}img{display:block}select{max-width:100%;padding:12px}.scroll{overflow:auto}summary{cursor:pointer}p{max-width:1100px}</style><h1>DOCX locations — Bhuvan historical imagery</h1><p>72 entries / 70 unique coordinates / 10 tiles / 5 usable period layers. Choose your address to jump to its tile. Images open at their original size. Nearby addresses can share a tile.</p><p>These are map-display images. Period names are provider mosaic labels, not exact acquisition dates. Coordinates are derived from the WMS grid (EPSG:3857). Watermarks are preserved. 2025 and 2026 returned empty tiles; z17 checks returned a Bhuvan logo placeholder. They are not usable satellite imagery in this pack.</p><select onchange="location.hash=this.value"><option value="">Select DOCX address…</option>'''+options+'</select>'+''.join(rows)
(R/'index.html').write_text(page,encoding='utf-8')
print(json.dumps({'valid_images':len(valid),'mapped_entries':len(locs),'unique_locations':len({(l['latitude'],l['longitude']) for l in locs}),'identical_period_tile_pairs':len(duplicates)}))
