const $ = id => document.getElementById(id);
let timer = null;

function bytes(n) {
  if (!n) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < 3) {
    n /= 1024;
    i++
  }
  return n.toFixed(i ? 1 : 0) + ' ' + u[i]
}

function setupWorkspaces() {
  const set = (selector, name) => {
    const el = document.querySelector(selector);
    if (el) el.dataset.workspace = name
  };
  set('.hero', 'data');
  set('.metrics', 'data');
  set('.intake', 'data');
  set('.archive', 'data');
  set('#searchResults', 'discovery');
  document.querySelectorAll('.eyebrow').forEach(e => {
    if (e.textContent.includes('DISCOVERY')) e.textContent = '02 / SEARCH & DISCOVER'
  });
  const results = $('searchResults');
  if (results && !$('clusterResults')) {
    const box = document.createElement('div');
    box.id = 'clusterResults';
    box.className = 'cluster-results';
    results.parentNode.append(box)
  }
  const mark = (id, name) => {
    const el = $(id);
    if (el) {
      const panel = el.closest('.panel');
      if (panel) panel.dataset.workspace = name
    }
  };
  mark('indexBuildBtn', 'discovery');
  mark('compareBtn', 'compare');
  mark('evalRunBtn', 'reports');
  mark('reviewId', 'review');
  document.querySelectorAll('main > section.panel.workspace').forEach(p => {
    if (!p.dataset.workspace) p.dataset.workspace = 'discovery'
  })
}

function setupClusterNav() {
  const navs = [...document.querySelectorAll('.nav')];
  if (navs[1] && !document.querySelector('[data-cluster-nav]')) {
    const b = navs[1].cloneNode(true);
    b.dataset.clusterNav = '1';
    b.id = 'clusterNav';
    b.querySelector('span').textContent = '◎';
    b.querySelector('em')?.remove();
    b.append(document.createTextNode(' Clusters'));
    navs[1].parentNode.insertBefore(b, navs[2] || null)
  }
}

function injectClusters() {
  if ($('clustersPanel')) return;
  const anchor = [...document.querySelectorAll('main > section.panel.workspace')].find(x => x.dataset.workspace === 'discovery') || document.querySelector('.panel.workspace');
  if (!anchor) return;
  const s = document.createElement('section');
  s.id = 'clustersPanel';
  s.className = 'panel workspace';
  s.dataset.workspace = 'clusters';
  s.innerHTML = '<div class="panel-head"><div><div class="eyebrow">03 / CLUSTERS</div><h3>Location timelines & similar sites</h3></div><span class="tag">OFFLINE MODEL</span></div><div class="hint">Automatic after import. Same-location timelines collect observations across seasons. Similar sites discovers comparable places elsewhere; it is not a change timeline.</div><div class="cluster-view-tabs"><label for="clusterMode">View</label><select id="clusterMode" onchange="loadClusters()"><option value="temporal">Same-location timelines</option><option value="similar">Similar sites across locations</option></select></div><div id="clusterList" class="cluster-list"><button id="loadClusters">LOAD CLUSTERS</button></div>';
  anchor.parentNode.insertBefore(s, anchor.nextSibling);
  $('loadClusters').onclick = loadClusters
}
let clusterPoll;

function clusterEscape(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  } [c]))
}
async function loadClusters() {
  clearTimeout(clusterPoll);
  const box = $('clusterList');
  if (!box) return;
  try {
    const response = await fetch('/api/clusters/status');
    if (!response.ok) throw new Error('status unavailable');
    const status = await response.json();
    // A persisted backend build is authoritative. localStorage only records
    // an in-progress UI action and must not hide ready groups after restart.
    if (status.state === 'waiting' && localStorage.getItem('anveshanClusterBuildApproved') !== '1') {
      box.innerHTML = '<div class="hint" role="status">Clusters are locked until you press BUILD LOCAL INDEX. Importing files alone does not create groups.</div>';
      return
    }
    if ((status.total || 0) === 0) {
      box.innerHTML = '<div class="hint" role="status">No imagery in the local archive yet. Import a folder in Data Library, then return here and press BUILD LOCAL INDEX.</div>';
      return
    }
    if (status.state === 'error') {
      box.textContent = 'Automatic clustering needs attention: ' + status.error;
      return
    }
    if (status.state !== 'ready') {
      const done = Number(status.done || 0),
        total = Number(status.total || 0),
        pct = total ? Math.min(100, Math.round(done / total * 100)) : 0;
      const started = Number(localStorage.getItem('anveshanClusterBuildStarted') || 0),
        elapsed = started ? Math.max(1, (Date.now() - started) / 1000) : 0;
      const rate = done > 0 && elapsed ? done / elapsed : 0,
        remaining = rate ? Math.ceil((total - done) / rate) : null;
      const finalPhase = /verif|group|match/i.test(status.state);
      const elapsedText = started ? `elapsed ${Math.floor(elapsed/60)}m ${Math.floor(elapsed%60)}s` : 'elapsed time starting';
      const loading = /loading/i.test(status.state);
      const tiling = /tiles/i.test(status.state);
      const eta = `${elapsedText} · ${loading ? 'Preparing the local model before image processing starts' : tiling ? 'Encoding image tiles locally' : finalPhase ? 'Verifying relationships; duration depends on candidate pairs' : remaining == null ? 'Measuring processing rate' : `about ${remaining}s remaining for image screening`}`;
      const embedded = done >= total && total > 0,
        verifying = /verif|group|match/i.test(status.state);
      const steps = [
        [embedded, 'Image screening + embeddings', embedded ? `${total.toLocaleString()} / ${total.toLocaleString()} complete` : `${done.toLocaleString()} / ${total.toLocaleString()} processed`],
        [false, 'Same-location RootSIFT/RANSAC verification', verifying ? 'running now' : 'waiting'],
        [tiling, 'Pair relationships and temporal groups', tiling ? 'complete' : 'pending'],
        [false, 'Local CPU processing', clusterEscape(status.current || 'active on this computer')],
        [false, 'READY + groups count', 'shown after verification']
      ];
      const progressLabel = loading ? 'Preparing model…' : tiling ? 'Encoding tiles…' : finalPhase ? 'Verifying…' : `${done.toLocaleString()} / ${total.toLocaleString()} images · ${pct}%`;
      box.innerHTML = `<div class="cluster-progress" role="status" aria-live="polite"><div class="cluster-progress-head"><b>${clusterEscape(status.state)}</b><span>${done.toLocaleString()} / ${total.toLocaleString()} images · ${pct}%</span></div><div class="cluster-progress-track"><div class="cluster-progress-fill" style="width:${pct}%"></div></div><div class="cluster-steps">${steps.map(([ok,label,detail],i)=>{const active=!ok&&((i===1&&verifying)||(i===3));const width=i===0?pct:ok?100:0;return `<div class="cluster-step ${ok?'complete':''} ${active?'active':''}"><span class="cluster-step-mark">${ok?'✓':active?'◉':'○'}</span><span class="cluster-step-body"><b>${label}</b><small>${detail}</small><span class="cluster-step-track"><span class="cluster-step-fill ${active?'indeterminate':''}" style="width:${width}%"></span></span></span></div>`}).join('')}</div><small>${eta}</small></div>`;
      box.querySelector('.cluster-progress-head span').textContent = progressLabel;
      box.querySelector('.cluster-progress-fill').classList.toggle('indeterminate', loading || tiling || finalPhase);
      clusterPoll = setTimeout(loadClusters, 2500);
      return;
    }
    const result = await fetch('/api/clusters?limit=100&mode=' + ($('clusterMode')?.value || 'temporal'));
    if (!result.ok) throw new Error('groups unavailable');
    const d = await result.json();
    box.innerHTML = `<div class="hint" role="status">${d.length} groups · ${status.unmatched||0} unmatched images · ${status.excluded||0} withheld for review · ${status.duplicates||0} duplicate copies hidden.<br>Same-location timelines use georeferencing or structural image matching. Dates/periods are supplied metadata; grouping accuracy is not yet independently measured.</div>`;
    box.innerHTML += d.length ? d.map(g => `<article class="cluster-card"><div><b>${clusterEscape(g.key)}</b><span>${g.count} scenes · ${clusterEscape(g.dates.join(', ')||'dates unavailable')}</span></div><p class="hint">${g.key.startsWith("sites-")?"Comparable appearances at different sites — not a change timeline":g.location_verified?"Same-location group · embedded footprints agree":"Same-location candidate · structural matching; inspect alignment"}</p><div class="cluster-thumbs">${g.scenes.slice(0,8).map(x=>`<img loading="lazy" src="/api/scenes/${x.id}/preview" alt="${clusterEscape(x.name)}" title="Scene ${x.id}">`).join('')}</div><button class="cluster-open" onclick="openCluster('${g.key}')">VIEW ALL IMAGES ↗</button>${g.key.startsWith("place-")?`<button onclick="checkClusterReadiness(this, '${g.key}')">CHECK COMPARISON READINESS</button><div class="pair-readiness" role="status"></div>`:""}</article>`).join('') : '<p class="hint">No verified groups in this view yet. Images are not forced into a group.</p>';
    if (status.review?.length) box.innerHTML += `<details><summary>Withheld images — inspect screening decisions (${status.review.length})</summary><div class="cluster-review-grid">${status.review.map(x=>`<figure><img loading="lazy" src="/api/scenes/${x.id}/preview" alt="${clusterEscape(x.name)}"><figcaption>${clusterEscape(x.name)}<br>${clusterEscape(x.reason)}</figcaption></figure>`).join('')}</div></details>`;
    if (status.unmatched_scene_ids?.length) box.innerHTML += `<details><summary>Satellite candidates without a confident group (${status.unmatched_scene_ids.length})</summary><div class="cluster-review-grid">${status.unmatched_scene_ids.map(id=>`<figure><img loading="lazy" src="/api/scenes/${id}/preview" alt="Scene ${id}"><figcaption>Scene ${id}</figcaption></figure>`).join('')}</div></details>`;
  } catch (e) {
    box.textContent = 'Cluster service unavailable: ' + e.message
  }
}

async function openCluster(key) {
  let modal = $('clusterModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'clusterModal';
    modal.className = 'cluster-modal';
    modal.innerHTML = '<div class="cluster-modal-card"><div class="cluster-modal-head"><div><div class="eyebrow">GROUP EVIDENCE</div><h3 id="clusterModalTitle"></h3></div><button class="modal-secondary" onclick="closeCluster()">CLOSE</button></div><div class="cluster-actions"><span id="clusterSelectionHint">Select any 2+ images to inspect together.</span><button id="clusterFullBtn" class="modal-secondary" onclick="fullscreenClusterSelected()">FULL SCREEN SELECTED</button><button id="clusterCompareBtn" class="query-row button" onclick="compareClusterSelected()">COMPARE SELECTED</button></div><div id="clusterModalGrid" class="cluster-modal-grid"></div></div>';
    document.body.append(modal);
    modal.onclick = e => {
      if (e.target === modal) closeCluster()
    }
  }
  modal.classList.add('open');
  $('clusterModalTitle').textContent = key;
  $('clusterSelectionHint').title = key.startsWith('sites-') ? 'Different sites: side-by-side visual inspection, not temporal change evidence' : 'Same-location observations across supplied periods';
  $('clusterModalGrid').textContent = 'Loading all available dates…';
  const d = await fetch('/api/clusters?limit=500&mode=' + ($('clusterMode')?.value || 'temporal')).then(r => r.json());
  const g = d.find(x => x.key === key);
  window.activeClusterScenes = g ? g.scenes : [];
  $('clusterModalGrid').innerHTML = window.activeClusterScenes.length ? window.activeClusterScenes.map(x => `<label class="cluster-pick"><input type="checkbox" value="${x.id}" onchange="updateClusterSelection()"><img src="/api/scenes/${x.id}/preview" alt="${clusterEscape(x.name)}"><figcaption>${clusterEscape(x.name)} · ${clusterEscape(x.period_label||x.date||'date unavailable')} · scene ${x.id}</figcaption></label>`).join('') : 'No readable previews available.';
  updateClusterSelection()
}

function updateClusterSelection() {
  const selected = [...document.querySelectorAll('#clusterModalGrid input:checked')];
  $('clusterSelectionHint').textContent = `${selected.length} selected · choose any 2+ images`;
  $('clusterCompareBtn').disabled = selected.length < 2;
  $('clusterFullBtn').disabled !== undefined && ($('clusterFullBtn').disabled = selected.length !== 1)
}

function fullscreenClusterSelected() {
  const id = Number(document.querySelector('#clusterModalGrid input:checked')?.value);
  if (!id) return;
  const scene = window.activeClusterScenes.find(x => x.id === id);
  if (!scene) return;
  let modal = $('singleImageModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'singleImageModal';
    modal.className = 'cluster-modal';
    modal.innerHTML = '<div class="single-image-card"><button class="modal-secondary" onclick="$(\'singleImageModal\').classList.remove(\'open\')">CLOSE</button><img id="singleImageView"><div id="singleImageCaption"></div></div>';
    document.body.append(modal);
    modal.onclick = e => {
      if (e.target === modal) modal.classList.remove('open')
    }
  }
  modal.classList.add('open');
  $('singleImageView').src = `/api/scenes/${id}/preview`;
  $('singleImageView').alt = scene.name;
  $('singleImageCaption').textContent = `${scene.name} · ${scene.period_label||scene.date||'date unavailable'} · scene ${scene.id}`
}

function compareClusterSelected() {
  const ids = [...document.querySelectorAll('#clusterModalGrid input:checked')].map(x => Number(x.value));
  if (ids.length < 2) return;
  const scenes = ids.map(id => window.activeClusterScenes.find(x => x.id === id)).filter(Boolean);
  let modal = $('comparisonModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'comparisonModal';
    modal.className = 'cluster-modal';
    modal.innerHTML = '<div class="cluster-modal-card"><div class="cluster-modal-head"><div><div class="eyebrow">MULTI-DATE COMPARISON</div><h3>Selected location evidence</h3></div><button class="modal-secondary" onclick="$(\'comparisonModal\').classList.remove(\'open\')">CLOSE</button></div><div class="compare-tools"><button onclick="setCompareMode(\'grid\')">SIDE BY SIDE</button><button onclick="setCompareMode(\'opacity\')">OPACITY</button><button onclick="setCompareMode(\'swipe\')">SWIPE</button><button onclick="setCompareMode(\'blink\')">BLINK</button><button onclick="playCompareTimeline()">PLAY TIMELINE</button><label>Opacity <input id="compareOpacity" type="range" min="10" max="100" value="50" oninput="setCompareOpacity(this.value)"></label></div><div id="comparisonGrid" class="cluster-modal-grid"></div></div>';
    document.body.append(modal)
  }
  modal.classList.add('open');
  window.compareScenes = scenes;
  $('comparisonGrid').innerHTML = scenes.map((x, i) => `<figure class="compare-frame frame-${i}"><img src="/api/scenes/${x.id}/preview" alt="${x.name}"><figcaption>${x.name} · ${x.period_label||x.date||'date unavailable'} · scene ${x.id}</figcaption></figure>`).join('');
  setCompareMode('grid')
}

function setCompareMode(mode) {
  const grid = $('comparisonGrid');
  if (!grid) return;
  clearInterval(window.compareTimer);
  grid.className = 'cluster-modal-grid compare-mode-' + mode;
  if (mode === 'swipe' && window.compareScenes?.length >= 2) {
    const a = window.compareScenes[0],
      b = window.compareScenes[1];
    grid.innerHTML = `<div class="swipe-stage"><img src="/api/scenes/${a.id}/preview"><div class="swipe-after"><img src="/api/scenes/${b.id}/preview"></div><input class="swipe-range" type="range" min="0" max="100" value="50" oninput="this.previousElementSibling.style.width=this.value+'%'"> </div>`
  } else if (window.compareScenes && (!grid.querySelector('.compare-frame'))) {
    grid.innerHTML = window.compareScenes.map((x, i) => `<figure class="compare-frame frame-${i}"><img src="/api/scenes/${x.id}/preview" alt="${x.name}"><figcaption>${x.name} · ${x.period_label||x.date||'date unavailable'} · scene ${x.id}</figcaption></figure>`).join('')
  }
}

function setCompareOpacity(value) {
  const frames = document.querySelectorAll('#comparisonGrid .compare-frame img');
  if (frames.length > 1) frames[1].style.opacity = Number(value) / 100
}

function playCompareTimeline() {
  const frames = [...document.querySelectorAll('#comparisonGrid .compare-frame')];
  if (frames.length < 2) return;
  let i = 0;
  clearInterval(window.compareTimer);
  window.compareTimer = setInterval(() => {
    frames.forEach((f, n) => f.classList.toggle('timeline-active', n === i));
    i = (i + 1) % frames.length
  }, 900)
}

function closeCluster() {
  const modal = $('clusterModal');
  if (modal) modal.classList.remove('open')
}

function setupIntakeControls() {
  const row = document.querySelector('.path-row');
  if (row && !$('chooseFolder')) {
    const choose = document.createElement('button');
    choose.id = 'chooseFolder';
    choose.type = 'button';
    choose.textContent = 'SELECT FOLDER';
    choose.onclick = async () => {
      choose.disabled = true;
      try {
        const response = await fetch('/api/pick-folder');
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || 'Native folder picker unavailable.');
        if (result.folder) {
          $('folder').value = result.folder;
          const hint = document.getElementById('folderHint');
          if (hint) hint.textContent = `Selected folder: ${result.folder}. Press SCAN FOLDER to begin local processing.`;
        }
      } catch (error) {
        const hint = document.getElementById('folderHint');
        if (hint) hint.textContent = error.message;
      } finally {
        choose.disabled = false;
      }
    };
    row.append(choose);
  }
  const hint = document.querySelector('.intake .hint');
  if (hint && !$('folderHint')) {
    hint.id = 'folderHint';
    hint.textContent = 'Paste the full absolute path for reliable offline scanning, or use SELECT FOLDER to identify the root folder.'
  }
  const archive = document.querySelector('.archive .panel-head');
  if (archive && !$('clearLibrary')) {
    const clear = document.createElement('button');
    clear.id = 'clearLibrary';
    clear.className = 'danger';
    clear.type = 'button';
    clear.textContent = 'CLEAR LOCAL ARCHIVE';
    clear.onclick = () => openClearModal();
    archive.append(clear);
  }
}

function openClearModal() {
  let modal = $('clearModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'clearModal';
    modal.className = 'modal-backdrop';
    modal.innerHTML = '<div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="clearModalTitle"><div class="modal-kicker">DESTRUCTIVE LOCAL ACTION</div><h3 id="clearModalTitle">Clear local archive?</h3><p>This will remove all indexed scenes and local fingerprints from the workstation. Original image files on disk will not be deleted.</p><div class="modal-actions"><button id="cancelClear" class="modal-secondary">NO, KEEP DATA</button><button id="confirmClear" class="modal-danger">YES, CLEAR ARCHIVE</button></div></div>';
    document.body.append(modal);
    $('cancelClear').onclick = closeClearModal;
    $('confirmClear').onclick = clearLibrary;
    modal.onclick = e => {
      if (e.target === modal) closeClearModal()
    };
  }
  modal.classList.add('open');
  $('cancelClear').focus();
}

function closeClearModal() {
  const modal = $('clearModal');
  if (modal) modal.classList.remove('open')
}
async function clearLibrary() {
  const btn = $('confirmClear');
  if (btn) btn.disabled = true;
  try {
    const r = await fetch('/api/library', {
      method: 'DELETE'
    });
    closeClearModal();
    if (r.ok) {
      localStorage.removeItem('anveshanClusterBuildApproved');
      localStorage.removeItem('anveshanClusterBuildStarted');
      refresh();
      refreshIndex();
      if ($('clusterList')) loadClusters()
    } else alert('Could not clear the local archive.')
  } catch (e) {
    closeClearModal();
    alert('Could not clear the local archive.')
  } finally {
    if (btn) btn.disabled = false
  }
}

function showWorkspace(name) {
  document.querySelectorAll('main > section').forEach(el => {
    const keep = el.dataset.workspace === name || (name === 'status' && el.classList.contains('metrics'));
    el.classList.toggle('workspace-hidden', !keep)
  });
  const nav = [...document.querySelectorAll('.nav')];
  nav.forEach(x => x.classList.remove('active'));
  const idx = {
    data: 0,
    discovery: 1,
    clusters: 2,
    compare: 3,
    review: 4,
    reports: 5,
    status: 6
  } [name];
  if (nav[idx]) nav[idx].classList.add('active');
  const titles = {
    data: 'Data Library',
    discovery: 'Search & Discover',
    clusters: 'Clusters',
    compare: 'Compare Timeline',
    review: 'Review Queue',
    reports: 'Reports & Provenance',
    status: 'System Status'
  };
  const h = document.querySelector('header h1');
  if (h) h.innerHTML = `${titles[name]||'Data Library'} <span>//</span> ${name==='discovery'?'Visual retrieval':name==='clusters'?'Visual similarity':name==='compare'?'Change workspace':name==='review'?'Decision record':name==='reports'?'Audit exports':'Offline archive'}`;
  if (name === 'clusters') loadClusters();
  window.scrollTo({
    top: 0,
    behavior: 'smooth'
  })
}

function wireNav() {
  const nav = [...document.querySelectorAll('.nav')];
  const names = ['data', 'discovery', 'clusters', 'compare', 'review', 'reports', 'status'];
  nav.forEach((btn, i) => btn.onclick = () => showWorkspace(names[i]));
  showWorkspace('data')
}

function injectCompare() {
  if ($('compareBtn')) return;
  const panels = document.querySelectorAll('.panel.workspace');
  const review = panels[panels.length - 1];
  const s = document.createElement('section');
  s.className = 'panel workspace';
  s.innerHTML = '<div class="panel-head"><div><div class="eyebrow">04 / CHANGE WORKSPACE</div><h3>Before / after evidence review</h3></div><span class="tag">SOURCE LINKED</span></div><div class="review-row"><input id="beforeId" type="number" placeholder="Before scene ID"><input id="afterId" type="number" placeholder="After scene ID"><button id="compareBtn">COMPARE SCENES ↗</button><button id="timelineBtn">BUILD TIMELINE</button><button id="pairsBtn">SUGGEST PAIRS</button><button id="footprintBtn">SHOW FOOTPRINTS</button></div><div id="compareStatus" class="hint">Select two indexed scenes from Discovery, then compare.</div><div id="compareView" class="compare-grid"></div><div id="timelineView" class="hint"></div><div id="pairsView" class="hint"></div><div id="footprintView" class="hint"></div>';
  review.parentNode.insertBefore(s, review);
  $('compareBtn').onclick = doCompare;
  $('timelineBtn').onclick = loadTimeline;
  $('pairsBtn').onclick = loadPairs;
  $('footprintBtn').onclick = loadFootprints
}
async function loadTimeline() {
  const d = await fetch('/api/timeline?limit=200').then(r => r.json());
  $('timelineView').innerHTML = d.length ? '<b>LOCAL REVIEW COHORTS</b><br>' + d.slice(0, 12).map(g => `${g.cohort} · ${g.count} scene(s) · ${g.dated} dated`).join('<br>') : 'No timeline cohorts available.'
}
async function loadPairs() {
  const d = await fetch('/api/pairs?limit=20').then(r => r.json());
  $('pairsView').innerHTML = d.length ? '<b>PAIR SUGGESTIONS · METADATA ONLY</b><br>' + d.slice(0, 10).map((p, i) => `<button class="mini" onclick="usePair(${p.before.id},${p.after.id})">${p.before.id} → ${p.after.id}</button> <span>${p.before.name} / ${p.after.name} · ${p.quality_flags.join(', ')||'basic checks pass'} · location unverified</span><br>`).join('') : 'No compatible pairs found.'
}

function usePair(b, a) {
  $('beforeId').value = b;
  $('afterId').value = a;
  $('compareStatus').textContent = 'Pair selected. Run comparison to load source evidence.'
}

function injectReports() {
  const panel = [...document.querySelectorAll('.panel.workspace')].pop();
  if ($('exportBtn') || !panel) return;
  const b = document.createElement('div');
  b.className = 'review-row';
  b.innerHTML = '<button id="exportBtn">EXPORT PROVENANCE JSON</button><span id="exportStatus" class="hint"></span>';
  panel.appendChild(b);
  $('exportBtn').onclick = async () => {
    const id = Number($('reviewId').value);
    if (!id) {
      $('exportStatus').textContent = 'Enter a scene ID first.';
      return
    }
    const r = await fetch('/api/export/provenance?scene_id=' + id);
    if (!r.ok) {
      $('exportStatus').textContent = 'Scene not found.';
      return
    }
    const blob = new Blob([JSON.stringify(await r.json(), null, 2)], {
      type: 'application/json'
    });
    const u = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = u;
    a.download = 'anveshan-provenance-' + id + '.json';
    a.click();
    URL.revokeObjectURL(u);
    $('exportStatus').textContent = 'Provenance export prepared locally.'
  }
}

function injectIndex() {
  if ($('indexBuildBtn')) return;
  const anchor = [...document.querySelectorAll('.panel.workspace')][0];
  if (!anchor) return;
  const s = document.createElement('section');
  s.className = 'panel workspace';
  s.innerHTML = '<div class="panel-head"><div><div class="eyebrow">01 / LOCAL VISUAL INDEX</div><h3>Prepare archive for visual retrieval</h3></div><span class="tag">OFFLINE ONLY</span></div><div class="review-row"><button id="indexBuildBtn">BUILD LOCAL INDEX</button><button id="indexRefreshBtn">CHECK INDEX STATUS</button></div><div id="indexStatus" class="hint">Index status has not been checked.</div><div class="hint">This build uses the installed local thumbnail fingerprint baseline. It does not claim semantic AI search until a validated offline encoder is indexed.</div>';
  anchor.parentNode.insertBefore(s, anchor);
  $('indexBuildBtn').onclick = buildIndex;
  $('indexRefreshBtn').onclick = refreshIndex;
  refreshIndex()
}

function injectEvaluation() {
  if ($('evalRunBtn')) return;
  const anchor = [...document.querySelectorAll('.panel.workspace')][1];
  if (!anchor) return;
  const s = document.createElement('section');
  s.className = 'panel workspace';
  s.innerHTML = '<div class="panel-head"><div><div class="eyebrow">05 / EVALUATION</div><h3>Measure the screening baseline</h3></div><span class="tag">LOCAL · LABELLED</span></div><div class="hint">Use a held-out local CSV or JSON manifest. Labels are supplied by the analyst; results are benchmark evidence, not a production accuracy claim.</div><div class="path-row"><label>MANIFEST PATH</label><input id="evalManifest" placeholder="C:\\evaluation\\heldout_pairs.csv"><button id="evalRunBtn">RUN BENCHMARK ↗</button></div><div class="review-row"><button id="evalSummaryBtn">CHECK READINESS</button><input id="evalRows" placeholder="Manual pairs: before_id,after_id,label" style="min-width:300px"><button id="evalMetricsBtn">SCORE MANUAL PAIRS</button></div><div id="evalStatus" class="hint">No evaluation has been run.</div><pre id="evalResults" class="hint" style="white-space:pre-wrap;max-height:260px;overflow:auto"></pre>';
  anchor.parentNode.insertBefore(s, anchor.nextSibling);
  $('evalRunBtn').onclick = runManifestEvaluation;
  $('evalSummaryBtn').onclick = loadEvaluationSummary;
  $('evalMetricsBtn').onclick = scoreManualPairs
}

function showEval(data) {
  $('evalResults').textContent = JSON.stringify(data, null, 2);
  const m = data.metrics;
  if (m) {
    $('evalStatus').textContent = `Labelled screening benchmark · ${data.evaluated_pairs||data.pairs?.length||0} pair(s) · precision ${m.precision??'—'} · recall ${m.recall??'—'} · false alarm ${m.false_alarm_rate??'—'}`;
  } else if (data.note) $('evalStatus').textContent = data.note;
}
async function loadEvaluationSummary() {
  const r = await fetch('/api/evaluation/summary');
  const d = await r.json();
  showEval(d);
  $('evalStatus').textContent = `Archive readiness · ${d.ready_scenes||0}/${d.indexed_scenes||0} ready · ${d.dated_scenes||0} dated · ${d.crs_declared_scenes||0} with CRS. Accuracy remains pending labelled data.`
}
async function runManifestEvaluation() {
  const manifest = $('evalManifest').value.trim();
  if (!manifest) {
    $('evalStatus').textContent = 'Enter a local CSV or JSON manifest path.';
    return
  }
  $('evalRunBtn').disabled = true;
  $('evalStatus').textContent = 'Running labelled benchmark locally…';
  try {
    const r = await fetch('/api/evaluation/run', {
      method: 'POST',
      headers: {
        'content-type': 'application/json'
      },
      body: JSON.stringify({
        manifest
      })
    });
    const d = await r.json();
    if (!r.ok) {
      $('evalStatus').textContent = d.detail || 'Benchmark failed.';
      return
    }
    showEval(d)
  } catch (e) {
    $('evalStatus').textContent = 'Benchmark unavailable; confirm the local server is running.'
  } finally {
    $('evalRunBtn').disabled = false
  }
}
async function scoreManualPairs() {
  const rows = $('evalRows').value.split(';').map(x => x.trim()).filter(Boolean);
  const pairs = [];
  for (const row of rows) {
    const p = row.split(',').map(x => x.trim());
    if (p.length !== 3 || !p.every(Boolean)) {
      $('evalStatus').textContent = 'Use semicolon separated pairs: before_id,after_id,label; …';
      return
    }
    pairs.push({
      before_id: Number(p[0]),
      after_id: Number(p[1]),
      label: Number(p[2])
    })
  }
  if (!pairs.length) {
    $('evalStatus').textContent = 'Enter at least one labelled pair.';
    return
  }
  $('evalMetricsBtn').disabled = true;
  $('evalStatus').textContent = 'Scoring labelled pairs locally…';
  try {
    const r = await fetch('/api/evaluation/metrics', {
      method: 'POST',
      headers: {
        'content-type': 'application/json'
      },
      body: JSON.stringify({
        pairs
      })
    });
    const d = await r.json();
    if (!r.ok) {
      $('evalStatus').textContent = d.detail || 'Metric calculation failed.';
      return
    }
    showEval(d)
  } catch (e) {
    $('evalStatus').textContent = 'Metric calculation unavailable.'
  } finally {
    $('evalMetricsBtn').disabled = false
  }
}
async function refreshIndex() {
  const el = $('indexStatus');
  if (!el) return;
  try {
    const d = await fetch('/api/index/status').then(r => r.json());
    el.textContent = `${d.indexed} indexed · ${d.ready_scenes} ready scene(s) · ${d.pending} pending · ${d.complete?'READY FOR LOCAL RETRIEVAL':'INDEX BUILD REQUIRED'} · encoder: ${d.encoder}`;
  } catch (e) {
    el.textContent = 'Index status unavailable; confirm the local server is running.'
  }
}
async function buildIndex() {
  const b = $('indexBuildBtn'),
    el = $('indexStatus');
  b.disabled = true;
  el.textContent = 'Starting local index build…';
  try {
    const r = await fetch('/api/index/build', {
        method: 'POST'
      }),
      j = await r.json();
    if (!r.ok) {
      el.textContent = j.detail || 'Index build could not start.';
      return
    }
    el.textContent = 'Index build running locally…';
    const poll = setInterval(async () => {
      try {
        const x = await fetch('/api/jobs/' + j.id).then(r => r.json());
        el.textContent = `LOCAL INDEX · ${x.state.toUpperCase()} · ${x.done||0} / ${x.total||0}${x.current?' · '+x.current:''}`;
        if (['complete', 'failed'].includes(x.state)) {
          clearInterval(poll);
          b.disabled = false;
          // A failure must stay on screen with its reason, not be replaced by status.
          if (x.state === 'failed') el.textContent = `LOCAL INDEX · FAILED · ${x.error || 'see log'}`;
          else refreshIndex()
        }
      } catch (e) {
        clearInterval(poll);
        b.disabled = false;
        el.textContent = 'Index progress unavailable.'
      }
    }, 350);
  } catch (e) {
    b.disabled = false;
    el.textContent = 'Index build failed to start.'
  }
}
async function loadFootprints() {
  const b = Number($('beforeId').value),
    a = Number($('afterId').value);
  if (!b || !a) {
    $('footprintView').textContent = 'Enter both scene IDs first.';
    return
  }
  const d = await Promise.all([b, a].map(id => fetch('/api/scenes/' + id + '/footprint').then(r => r.json())));
  const ok = d.filter(x => x.available);
  if (!ok.length) {
    $('footprintView').innerHTML = '<b>NO FOOTPRINT EVIDENCE</b><br>Both scenes need sidecar bbox/footprint metadata. No map claim is made.';
    return
  }
  const labels = d.map(x => `${x.name}: ${x.available?'footprint available':'missing'}`).join(' · ');
  let svg = '';
  const boxes = d.map(x => {
    let v = x.footprint;
    if (Array.isArray(v) && v.length === 4 && v.every(Number.isFinite)) return v;
    if (v && v.bbox) return v.bbox;
    return null
  }).filter(Boolean);
  if (boxes.length) {
    const minX = Math.min(...boxes.map(v => v[0])),
      maxX = Math.max(...boxes.map(v => v[2])),
      minY = Math.min(...boxes.map(v => v[1])),
      maxY = Math.max(...boxes.map(v => v[3]));
    const sx = x => 20 + (x - minX) / (maxX - minX || 1) * 360,
      sy = y => 260 - (y - minY) / (maxY - minY || 1) * 220;
    svg = '<svg viewBox="0 0 400 280" style="width:100%;max-width:500px;background:#101711;border:1px solid #40513c"><path d="M20 260H380M20 260V20" stroke="#65785b"/><text x="25" y="18" fill="#b8c9a8" font-size="11">LOCAL FOOTPRINT PLOT · NO BASEMAP</text>' + boxes.map((v, i) => `<rect x="${sx(v[0])}" y="${sy(v[3])}" width="${Math.max(3,sx(v[2])-sx(v[0]))}" height="${Math.max(3,sy(v[1])-sy(v[3]))}" fill="${i?'#e0a84b':'#77b86a'}" fill-opacity=".35" stroke="${i?'#e0a84b':'#77b86a'}"/><text x="${sx(v[0])+3}" y="${sy(v[3])+14}" fill="white" font-size="10">${i?'AFTER':'BEFORE'}</text>`).join('') + '</svg>'
  }
  $('footprintView').innerHTML = '<b>LOCAL FOOTPRINT CHECK</b><br>' + labels + '<br><small>CRS: ' + d.map(x => x.crs || 'undeclared').join(' / ') + ' · Render source: local sidecar metadata</small><br>' + svg
}
async function refresh() {
  const s = await fetch('/api/status').then(r => r.json());
  // Rejected files (blank tiles, corrupt rasters) are imported records, not usable scenes.
  $('sceneCount').textContent = (s.scenes - s.errors).toLocaleString();
  $('size').textContent = bytes(s.bytes);
  $('health').textContent = s.errors ? 'CHECK' : 'READY';
  $('healthSub').textContent = s.errors ? `${s.errors} file(s) need attention` : 'No failures recorded';
  $('sceneSub').textContent = s.scenes ? `${s.scenes.toLocaleString()} imported · ${s.errors} rejected` : 'Awaiting first import';
  if ($('modelSub')) $('modelSub').textContent = s.semantic_index || s.model;
  loadScenes()
}
async function loadScenes() {
  const rows = await fetch('/api/scenes?q=' + encodeURIComponent($('filter').value)).then(r => r.json());
  $('empty').classList.toggle('hidden', rows.length > 0);
  $('table').classList.toggle('hidden', !rows.length);
  $('rows').innerHTML = rows.map(r => `<div class="row"><span class="name">${r.name}<small>${r.path}</small></span><span>${r.kind}</span><span>${r.width||'—'} × ${r.height||'—'} · ${r.bands||'?'} band</span><span>${r.crs||'Not declared'}</span><span><i class="badge ${r.status==='error'?'error':''}">${r.status==='error'?'ERROR':'READY'}</i></span></div>`).join('')
}

function watch(id) {
  clearInterval(timer);
  timer = setInterval(async () => {
    const j = await fetch('/api/jobs/' + id).then(r => r.json());
    $('progressState').textContent = j.state.toUpperCase();
    $('progressCount').textContent = `${j.done} / ${j.total}`;
    $('bar').style.width = j.total ? `${j.done/j.total*100}%` : '8%';
    $('current').textContent = j.current || j.error || '';
    if (['complete', 'failed'].includes(j.state)) {
      clearInterval(timer);
      if (j.state === 'complete') localStorage.removeItem('anveshanClusterBuildApproved');
      refresh();
      loadClusters()
    }
  }, 350)
}
function confirmDestructiveImport() {
  // "replace" empties the whole archive. It used to be the default, and one
  // stray click has already cost 165 scenes.
  if (($('importMode')?.value || 'append') !== 'replace') return true;
  return confirm('Replace archive?\n\nEvery scene and index already imported will be deleted. This cannot be undone.')
}
async function ingestSelectedFiles() {
  if (!window.selectedFolderFiles?.length) return;
  if (!confirmDestructiveImport()) return;
  $('progress').classList.remove('hidden');
  $('progressState').textContent = 'UPLOADING LOCALLY';
  const form = new FormData();
  form.append('mode', $('importMode')?.value || 'append');
  window.selectedFolderFiles.forEach(f => {
    form.append('files', f, f.name);
    form.append('paths', f.webkitRelativePath || f.name)
  });
  const j = await fetch('/api/scan/upload', {
    method: 'POST',
    body: form
  }).then(r => r.json());
  if (j.id) watch(j.id);
  else {
    $('progressState').textContent = 'FAILED';
    $('current').textContent = j.detail || 'Could not start scan.'
  }
}
$('scan').onclick = async () => {
  if (!confirmDestructiveImport()) return;
  const folder = $('folder').value.trim();
  if (!folder && window.selectedFolderFiles?.length) {
    ingestSelectedFiles();
    return
  }
  $('progress').classList.remove('hidden');
  if (!folder) {
    $('folder').focus();
    return
  }
  const j = await fetch('/api/scan', {
    method: 'POST',
    headers: {
      'content-type': 'application/json'
    },
    body: JSON.stringify({
      folder,
      mode: $('importMode')?.value || 'append'
    })
  }).then(r => r.json());
  if (j.id) watch(j.id);
  else {
    $('progressState').textContent = 'FAILED';
    $('current').textContent = j.detail || 'Could not start scan.'
  }
};
// A cosine similarity is a ranking cue, not a probability. Printing it as
// "37%" reads as 37% confidence, so show the raw score with its name.
function scoreText(score, type) {
  return `${(type || 'similarity').toUpperCase()} ${Number(score ?? 0).toFixed(3)} · RANKING SCORE, NOT A PERCENTAGE`;
}

async function doSearch() {
  const p = new URLSearchParams({
    q: $('query').value,
    date_from: $('from').value,
    date_to: $('to').value
  });
  const d = await fetch('/api/search?' + p).then(r => r.json());
  $('searchResults').innerHTML = d.results.length ? d.results.map(r => `<article class="result"><div class="result-visual"><img class="result-thumb" src="/api/scenes/${r.id}/preview" alt="Preview of ${r.name}" loading="lazy"><a class="image-link" href="/api/scenes/${r.id}/preview" target="_blank" rel="noopener">OPEN FULL IMAGE ↗</a></div><b>${r.name}</b><small>SCENE ID ${r.id} · ${r.kind} · ${r.width||'?'}×${r.height||'?'} · ${r.date||'date unknown'}</small><div class="score">${scoreText(r.match_score, r.score_type)}</div><button class="mini" onclick="pick(${r.id})">USE IN COMPARE</button><button class="mini" onclick="findSimilar(${r.id})">FIND SIMILAR SITES</button></article>`).join('') : `<div class="hint">No indexed scene matched these metadata filters. Text search does not inspect pixels until a validated semantic encoder is installed.</div>`
}
async function findSimilar(id) {
  const box = $('clusterResults');
  if (!box) return;
  box.textContent = 'Finding visually similar indexed scenes locally…';
  try {
    const d = await fetch(`/api/search/visual?scene_id=${id}&limit=12`).then(r => r.json());
    box.innerHTML = d.results?.length ? `<b>SIMILAR SITE CLUSTER · LOCAL VISUAL BASELINE</b><br><small>Reference scene ${id}; inspect members before treating them as the same location.</small><div class="cluster-grid">${d.results.map(r=>`<article class="result"><img class="result-thumb" src="/api/scenes/${r.id}/preview" alt="${r.name}"><b>${r.name}</b><small>${scoreText(r.match_score ?? r.visual_score, 'visual similarity')} · scene ${r.id}</small></article>`).join('')}</div>` : 'No indexed visual neighbours found.'
  } catch (e) {
    box.textContent = 'Visual clustering unavailable.'
  }
}

async function pick(id) {
  window.compareScenes = window.compareScenes || [];
  if (!window.compareScenes.some(s => s.id === id)) {
    const scene = await fetch(`/api/scenes/${id}`).then(r => r.ok ? r.json() : null);
    if (scene) window.compareScenes.push(scene)
  }
  if (window.compareScenes.length) $('beforeId').value = window.compareScenes[0].id;
  if (window.compareScenes.length > 1) $('afterId').value = window.compareScenes[1].id;
  showWorkspace('compare');
  if ($('compareView')) {
    $('compareView').innerHTML = window.compareScenes.map(x => `<article class="result"><b>${clusterEscape(x.name)}</b><small>SCENE ID ${x.id} · ${clusterEscape(x.date||'date unavailable')}</small><img src="/api/scenes/${x.id}/preview" alt="${clusterEscape(x.name)}" style="width:100%;margin-top:10px;max-height:360px;object-fit:contain;background:#101711"></article>`).join('')
  }
  if ($('compareStatus')) $('compareStatus').textContent = `${window.compareScenes.length} selected image(s). Add more from Search/Clusters or open the compare tool.`
}
async function doCompare() {
  const b = Number($('beforeId').value),
    a = Number($('afterId').value);
  if (!b || !a) {
    $('compareStatus').textContent = 'Enter both scene IDs to compare.';
    return
  }
  const r = await fetch(`/api/compare?before=${b}&after=${a}`);
  const d = await r.json();
  if (!r.ok) {
    $('compareStatus').textContent = d.detail || 'Comparison failed.';
    return
  }
  const card = x => `<article class="result"><b>${x.name}</b><small>SCENE ID ${x.id} · ${x.date||'date unknown'} · ${x.sensor||'sensor unknown'} · ${x.crs||'CRS unknown'}</small><img src="/api/scenes/${x.id}/preview" alt="${x.name}" style="width:100%;margin-top:10px;max-height:260px;object-fit:contain;background:#101711"><small>${x.width||'?'}×${x.height||'?'} · ${x.bands||'?'} band · ${x.kind}</small></article>`;
  $('compareView').innerHTML = card(d.before) + card(d.after);
  $('compareStatus').textContent = 'Both source scenes loaded locally. Analyst interpretation and decision remain required.'
}
$('searchBtn').onclick = doSearch;
$('saveReview').onclick = async () => {
  const scene_id = Number($('reviewId').value);
  if (!scene_id) return;
  const r = await fetch('/api/decisions', {
    method: 'POST',
    headers: {
      'content-type': 'application/json'
    },
    body: JSON.stringify({
      scene_id,
      decision: $('reviewDecision').value,
      note: $('reviewNote').value
    })
  });
  $('reviewStatus').textContent = r.ok ? 'Decision saved to local audit log.'
    : 'Could not save decision: ' + ((await r.json().catch(() => ({}))).detail || r.status);
};
$('filter').oninput = loadScenes;
setInterval(() => {
  const d = new Date();
  $('clock').textContent = d.toLocaleTimeString('en-IN', {
    hour12: false
  }) + ' IST'
}, 1000);
injectCompare();
injectIndex();
injectEvaluation();
injectReports();
injectClusters();
setupWorkspaces();
setupClusterNav();
setupIntakeControls();
window.addEventListener('load', setupIntakeControls);
wireNav();
refresh();

// The pixel score is a transparent screening cue. Keep it beside the source
// previews and quality gate so the operator cannot mistake it for semantic AI.
async function runChangeScore() {
  const b = Number($('beforeId').value),
    a = Number($('afterId').value);
  if (!b || !a) {
    $('compareStatus').textContent = 'Enter both scene IDs to score change.';
    return
  }
  const r = await fetch(`/api/change-score?before=${b}&after=${a}`);
  const d = await r.json();
  if (!r.ok) {
    $('compareStatus').textContent = d.detail || 'Change screening failed.';
    return
  }
  const pct = (Number(d.changed_pixel_ratio || 0) * 100).toFixed(1);
  const mad = Number(d.mean_absolute_difference || 0).toFixed(4);
  const flags = (Array.isArray(d.caveats) ? d.caveats : []).map(x => `<li>${x}</li>`).join('');
  $('compareStatus').innerHTML = `<b>CHANGE SCREENING · ${d.screening_label.toUpperCase()}</b><br><span class="score">${pct}% changed pixels</span> · mean difference ${mad} · threshold ${d.threshold}<br><small>Analysis status: ${d.analysis_status}. Inspect original imagery before recording a decision.</small>`;
  $('compareView').insertAdjacentHTML('beforeend', `<article class="result"><b>OFFLINE CHANGE SCREENING</b><small>Thumbnail ${d.thumbnail_size.width} × ${d.thumbnail_size.height} · source scenes ${d.before_id} → ${d.after_id}</small><div class="score">${pct}% PIXEL DIFFERENCE</div><div class="hint">Quality gate: review required · score is a prioritisation cue only</div><details><summary>Known caveats</summary><ul>${flags}</ul></details></article>`)
}
if ($('compareBtn')) {
  $('compareBtn').onclick = async () => {
    await doCompare();
    await runChangeScore()
  }
}
// PS 2.2.1 multimodal discovery controls. The officer can search by words or
// select one indexed image; both paths call the offline semantic endpoint.
function injectSearchControls() {
  const q = $('query');
  if (!q || $('referenceScene')) return;
  const select = document.createElement('select');
  select.id = 'referenceScene';
  select.title = 'Choose an indexed image for image-to-image search';
  select.innerHTML = '<option value="">TEXT SEARCH — choose reference image for image search</option>';
  q.parentNode.insertBefore(select, q.nextSibling);
  select.onchange = () => {
    q.placeholder = select.value ? 'Optional text filter (image mode)' : 'e.g. newly built structures near a river'
  };
  fetch('/api/scenes?limit=500').then(r => r.json()).then(rows => {
    select.innerHTML = '<option value="">TEXT SEARCH — choose reference image for image search</option>' + rows.filter(r => r.status === 'ready').map(r => `<option value="${r.id}">IMAGE ${r.id} · ${r.name} · ${r.date||'date unknown'}</option>`).join('')
  })
}
async function doSearch() {
  const ref = $('referenceScene')?.value;
  const p = new URLSearchParams({
    q: ref ? '' : $('query').value,
    reference_scene_id: ref || '',
    date_from: $('from').value,
    date_to: $('to').value,
    limit: '30',
    sensor: $('sensorFilter')?.value || '',
    bbox: $('bboxFilter')?.value || ''
  });
  const response = await fetch('/api/search/semantic?' + p);
  const d = await response.json();
  if (!response.ok) {
    $('searchResults').innerHTML = `<div class="hint">${d.detail||'Local semantic index is still preparing.'}</div>`;
    return
  }
  const mode = d.mode === 'image-to-image' ? 'Image-to-image' : 'Free-text';
  $('searchResults').innerHTML = (d.results.length ? `<div class="hint">${mode} results · ${d.encoder} · ranked offline. Similarity is a ranking score, not an accuracy percentage.</div>` : '<div class="hint">No indexed scene matched these filters.</div>') + (d.results || []).map(r => `<article class="result"><div class="result-visual"><img class="result-thumb" src="/api/scenes/${r.id}/preview" alt="Preview of ${r.name}" loading="lazy"><a class="image-link" href="/api/scenes/${r.id}/preview" target="_blank" rel="noopener">OPEN FULL IMAGE ↗</a></div><b>${r.name}</b><small>SCENE ID ${r.id} · ${r.kind} · ${r.width||'?'}×${r.height||'?'} · ${r.date||'date unknown'}</small><div class="score">${scoreText(r.match_score, r.score_type)}</div><button class="mini" onclick="pick(${r.id})">USE IN COMPARE</button><button class="mini" onclick="findSimilar(${r.id})">FIND SIMILAR SITES</button></article>`).join('')
}
window.addEventListener('load', () => {
  injectSearchControls();
  if ($('searchBtn')) $('searchBtn').onclick = doSearch
});
// Final officer workflow layout: Clusters before Search & Discover and with
// its own local-index status. Definitions here override the earlier baseline.
function setupClusterNav() {
  const navs = [...document.querySelectorAll('.nav')];
  if (navs[1] && !document.querySelector('[data-cluster-nav]')) {
    const b = navs[1].cloneNode(true);
    b.dataset.clusterNav = '1';
    b.id = 'clusterNav';
    b.querySelector('span').textContent = '◎';
    b.querySelector('em')?.remove();
    b.append(document.createTextNode(' Clusters'));
    navs[1].parentNode.insertBefore(b, navs[1])
  }
}

function injectClusters() {
  if ($('clustersPanel')) return;
  const anchor = [...document.querySelectorAll('main > section.panel.workspace')].find(x => x.dataset.workspace === 'discovery') || document.querySelector('.panel.workspace');
  if (!anchor) return;
  const s = document.createElement('section');
  s.id = 'clustersPanel';
  s.className = 'panel workspace';
  s.dataset.workspace = 'clusters';
  s.innerHTML = '<div class="panel-head"><div><div class="eyebrow">01 / LOCAL VISUAL INDEX + CLUSTERS</div><h3>Prepare archive & inspect locations</h3></div><span class="tag">OFFLINE MODEL</span></div><div class="review-row"><button id="clusterBuildIndex">BUILD LOCAL INDEX</button><button id="clusterIndexStatus">CHECK INDEX STATUS</button><span id="clusterIndexMessage" class="hint">Index status is checked automatically after import.</span></div><div class="hint">Same-location timelines collect all dates/seasons. Similar sites discovers comparable locations. Officers do not create clusters manually.</div><div class="cluster-view-tabs"><label for="clusterMode">View</label><select id="clusterMode"><option value="temporal">Same-location timelines</option><option value="similar">Similar sites across locations</option></select></div><div id="clusterList" class="cluster-list"><button id="loadClusters">LOAD CLUSTERS</button></div>';
  anchor.parentNode.insertBefore(s, anchor);
  $('clusterBuildIndex').onclick = () => buildIndex();
  $('clusterIndexStatus').onclick = refreshIndex;
  $('clusterMode').onchange = loadClusters;
  $('loadClusters').onclick = loadClusters
}

function injectSearchControls() {
  const q = $('query');
  if (!q || $('referenceScene')) return;
  const select = document.createElement('select');
  select.id = 'referenceScene';
  select.title = 'Choose an indexed satellite image for image-to-image search';
  select.innerHTML = '<option value="">TEXT SEARCH — type a query above</option>';
  q.parentNode.insertBefore(select, q.nextSibling);
  const upload = document.createElement('input');
  upload.type = 'file';
  upload.accept = 'image/png,image/jpeg,image/webp,image/tiff';
  upload.id = 'referenceUpload';
  upload.title = 'Upload a reference image for image-to-image search';
  q.parentNode.insertBefore(upload, select.nextSibling);
  const label = document.createElement('small');
  label.id = 'referenceLabel';
  label.textContent = 'Or upload reference image';
  q.parentNode.insertBefore(label, upload.nextSibling);
  upload.onchange = () => {
    if (upload.files.length) {
      select.value = '';
      q.value = '';
      label.textContent = 'Reference selected: ' + upload.files[0].name + ' — press SEARCH'
    }
  };
  fetch('/api/scenes?limit=500').then(r => r.json()).then(rows => {
    select.innerHTML = '<option value="">TEXT SEARCH — type a query above</option>' + rows.filter(r => r.status === 'ready').map(r => `<option value="${r.id}">INDEXED IMAGE ${r.id} · ${r.name} · ${r.date||'date unknown'}</option>`).join('')
  })
}
async function doSearch() {
  if (clusterResults) clusterResults.innerHTML = '';
  searchResults.innerHTML = '<div class=hint role=status>Matching reference imagery locally — checking image structure…</div>';
  const upload = $('referenceUpload')?.files?.[0];
  const ref = $('referenceScene')?.value;
  let response, d;
  if (upload && $('refineTextQuery')?.checked) throw Error('Clear text refinement to search using an uploaded image.');
  if (upload) {
    const f = new FormData();
    f.append('file', upload);
    f.append('date_from', $('from').value);
    f.append('date_to', $('to').value);
    response = await fetch('/api/search/semantic/upload?' + new URLSearchParams({
      date_from: $('from')?.value || '',
      date_to: $('to')?.value || '',
      sensor: $('sensorFilter')?.value || '',
      bbox: $('bboxFilter')?.value || ''
    }), {
      method: 'POST',
      body: f
    })
  } else {
    const p = new URLSearchParams({
      q: ref ? '' : $('query').value,
      reference_scene_id: ref || '',
      date_from: $('from').value,
      date_to: $('to').value,
      limit: '30',
      sensor: $('sensorFilter')?.value || '',
      bbox: $('bboxFilter')?.value || ''
    });
    if (!ref) p.delete('reference_scene_id');
    if ($('refineTextQuery')?.checked) {
      const ids = [...new Set((window.compareScenes || []).map(s => s.id))];
      if (ref || ids.length < 5) throw Error('For text refinement, select at least five relevant comparison images and clear the reference-image choice.');
      p.set('feedback_scene_ids', ids.join(','));
    }
    response = await fetch('/api/search/semantic?' + p)
  }
  d = await response.json();
  if (!response.ok) {
    $('searchResults').innerHTML = `<div class="hint">${d.detail||'Local semantic index is still preparing.'}</div>`;
    return
  }
  const mode = upload ? 'Uploaded image' : d.mode === 'image-to-image' ? 'Indexed image' : 'Free-text';
  $('searchResults').innerHTML = (d.results.length ? `<div class="hint">${mode} results · ${d.encoder} · ranked offline. Similarity is a ranking score, not an accuracy percentage.</div>` : '<div class="hint">No indexed scene matched these filters.</div>') + (d.results || []).map(r => `<article class="result"><div class="result-visual"><img class="result-thumb" src="/api/scenes/${r.id}/preview" alt="Preview of ${r.name}" loading="lazy"><a class="image-link" href="/api/scenes/${r.id}/preview" target="_blank" rel="noopener">OPEN FULL IMAGE ↗</a></div><b>${r.name}</b><small>SCENE ID ${r.id} · ${r.kind} · ${r.width||'?'}×${r.height||'?'} · ${r.date||'date unknown'}</small><div class="score">${scoreText(r.match_score, r.score_type)}</div><button class="mini" onclick="pick(${r.id})">USE IN COMPARE</button><button class="mini" onclick="findSimilar(${r.id})">FIND SIMILAR SITES</button></article>`).join('')
}

// Keep the visual-index card on Clusters and make navigation follow the
// visible workspace labels after the Clusters item is inserted.
function setupClusterNav() {
  const navs = [...document.querySelectorAll('.nav')];
  if (navs[1] && !document.querySelector('[data-cluster-nav]')) {
    const b = navs[1].cloneNode(true);
    b.dataset.clusterNav = '1';
    b.dataset.workspace = 'clusters';
    b.id = 'clusterNav';
    b.querySelector('span').textContent = '◎';
    b.querySelector('em')?.remove();
    b.append(document.createTextNode(' Clusters'));
    navs[1].parentNode.insertBefore(b, navs[1])
  }
  document.querySelectorAll('.nav').forEach(b => {
    if (b.dataset.workspace) return;
    const t = b.textContent.toLowerCase();
    b.dataset.workspace = t.includes('cluster') ? 'clusters' : t.includes('search') ? 'discovery' : t.includes('compare') ? 'compare' : t.includes('review') ? 'review' : t.includes('report') ? 'reports' : t.includes('status') ? 'status' : 'data'
  })
}

function showWorkspace(name) {
  document.querySelectorAll('main > section').forEach(el => {
    const keep = el.dataset.workspace === name || (name === 'status' && el.classList.contains('metrics'));
    el.classList.toggle('workspace-hidden', !keep)
  });
  document.querySelectorAll('.nav').forEach(x => x.classList.toggle('active', x.dataset.workspace === name));
  const titles = {
    data: 'Data Library',
    discovery: 'Search & Discover',
    clusters: 'Clusters',
    compare: 'Compare Timeline',
    review: 'Review Queue',
    reports: 'Reports & Provenance',
    status: 'System Status'
  };
  const h = document.querySelector('header h1');
  if (h) h.innerHTML = `${titles[name]||'Data Library'} <span>//</span> ${name==='discovery'?'Visual retrieval':name==='clusters'?'Visual similarity':name==='compare'?'Change workspace':name==='review'?'Decision record':name==='reports'?'Audit exports':'Offline archive'}`;
  if (name === 'clusters') {
    const index = document.querySelector('#indexBuildBtn')?.closest('section');
    if (index) index.dataset.workspace = 'clusters';
    loadClusters()
  }
  window.scrollTo({
    top: 0,
    behavior: 'smooth'
  })
}

function wireNav() {
  const nav = [...document.querySelectorAll('.nav')];
  nav.forEach(btn => btn.onclick = () => showWorkspace(btn.dataset.workspace));
  showWorkspace('data')
}

// One authoritative index card: it lives at the top of Clusters and reuses
// the existing index actions, so there is no second card at the page bottom.
function injectClusters() {
  const oldIndex = document.querySelector('#indexBuildBtn')?.closest('section');
  if (oldIndex) oldIndex.remove();
  if ($('clustersPanel')) return;
  const anchor = [...document.querySelectorAll('main > section.panel.workspace')].find(x => x.dataset.workspace === 'discovery') || document.querySelector('.panel.workspace');
  if (!anchor) return;
  const s = document.createElement('section');
  s.id = 'clustersPanel';
  s.className = 'panel workspace';
  s.dataset.workspace = 'clusters';
  s.innerHTML = '<div class="panel-head"><div><div class="eyebrow">01 / LOCAL VISUAL INDEX + CLUSTERS</div><h3>Prepare archive & inspect locations</h3></div><span class="tag">OFFLINE MODEL</span></div><div class="review-row"><button id="indexBuildBtn">BUILD LOCAL INDEX</button><button id="indexRefreshBtn">CHECK INDEX STATUS</button><span id="indexStatus" class="hint">Index status is checked automatically after import.</span></div><div class="hint">Same-location timelines collect all dates/seasons. Similar sites discovers comparable locations. Officers do not create clusters manually.</div><div class="cluster-view-tabs"><label for="clusterMode">View</label><select id="clusterMode"><option value="temporal">Same-location timelines</option><option value="similar">Similar sites across locations</option></select></div><div id="clusterList" class="cluster-list"><button id="loadClusters">LOAD CLUSTERS</button></div>';
  anchor.parentNode.insertBefore(s, anchor);
  $('indexBuildBtn').onclick = buildClusters;
  $('indexRefreshBtn').onclick = refreshIndex;
  $('clusterMode').onchange = loadClusters;
  $('loadClusters').onclick = loadClusters;
  refreshIndex();
}

async function buildClusters() {
  const b = $('indexBuildBtn'),
    status = $('indexStatus');
  if (b) b.disabled = true;
  localStorage.setItem('anveshanClusterBuildStarted', String(Date.now()));
  if (status) status.textContent = 'LOCAL INDEX + CLUSTERS · starting…';
  try {
    const [thumb] = await Promise.all([
      fetch('/api/index/build', {
        method: 'POST'
      }),
      fetch('/api/clusters/build', {
        method: 'POST'
      })
    ]);
    if (!thumb.ok) throw new Error('index build could not start');
    if (status) status.textContent = 'Screening, embedding and clustering locally…';
    localStorage.setItem('anveshanClusterBuildApproved', '1');
    loadClusters();
    const poll = setInterval(async () => {
      const s = await fetch('/api/clusters/status').then(r => r.json()).catch(() => ({}));
      if (s.state === 'ready' || s.state === 'error') {
        clearInterval(poll);
        localStorage.removeItem('anveshanClusterBuildStarted');
        if (b) b.disabled = false;
        if (status) status.textContent = s.state === 'ready' ? `${s.groups||0} groups ready · ${s.excluded||0} withheld for review` : 'Cluster build needs attention.'
      }
    }, 1200);
  } catch (e) {
    if (status) status.textContent = 'Build failed: ' + e.message;
    if (b) b.disabled = false
  }
}

// Evidence-bound change narrative. It uses measurements from the offline
// detector and never asks a language model to guess what an object is.
async function runChangeScore() {
  const b = Number($('beforeId').value),
    a = Number($('afterId').value);
  if (!b || !a) {
    $('compareStatus').textContent = 'Enter both scene IDs to score change.';
    return
  }
  const [scoreResponse, reportResponse] = await Promise.all([fetch(`/api/change-score?before=${b}&after=${a}`), fetch(`/api/change-report?before=${b}&after=${a}`)]);
  const d = await scoreResponse.json(),
    report = await reportResponse.json();
  if (!scoreResponse.ok) {
    $('compareStatus').textContent = d.detail || 'Change screening failed.';
    return
  }
  const pct = (Number(d.adjusted_changed_pixel_ratio || 0) * 100).toFixed(1);
  const flags = (Array.isArray(d.caveats) ? d.caveats : []).map(x => `<li>${x}</li>`).join('');
  $('compareStatus').innerHTML = `<b>CHANGE SCREENING · ${d.screening_label.toUpperCase()}</b><br><span class="score">${pct}% adjusted changed pixels</span> · mean difference ${d.mean_absolute_difference} · threshold ${d.threshold}<br><small>Analysis status: ${d.analysis_status}. Inspect original imagery before recording a decision.</small>`;
  $('compareView').insertAdjacentHTML('beforeend', `<article class="result change-report"><b>OFFLINE CHANGE REPORT</b><p>${report.narrative}</p><small>Evidence source: ${report.source} · LLM wording layer: not used · confidence: screening cue only</small><details><summary>Known caveats</summary><ul>${flags}</ul></details></article>`);
}

// Select any number of visual neighbours and carry them into Compare Timeline.
async function compareSelectedSimilar() {
  const ids = [...document.querySelectorAll('#similarResults input[type=checkbox]:checked')].map(x => Number(x.value));
  if (ids.length < 2) {
    const h = $('similarSelectionHint');
    if (h) h.textContent = 'Select at least 2 images.';
    return
  }
  const scenes = await Promise.all(ids.map(id => fetch(`/api/scenes/${id}`).then(r => r.ok ? r.json() : null)));
  window.compareScenes = scenes.filter(Boolean);
  showWorkspace('compare');
  if (window.compareScenes.length >= 2) {
    $('beforeId').value = window.compareScenes[0].id;
    $('afterId').value = window.compareScenes[1].id;
    $('compareStatus').textContent = `${window.compareScenes.length} selected images loaded. Use the timeline view to inspect them together.`;
    $('compareView').innerHTML = window.compareScenes.map((x, i) => `<article class="result"><b>${x.name}</b><small>SCENE ID ${x.id} · ${x.date||'date unavailable'}</small><img src="/api/scenes/${x.id}/preview" alt="${x.name}" style="width:100%;margin-top:10px;max-height:360px;object-fit:contain;background:#101711"></article>`).join('')
  }
}

function findSimilar(id) {
  const box = $('clusterResults');
  if (!box) return;
  box.textContent = 'Finding visually similar indexed scenes locally…';
  fetch(`/api/search/visual?scene_id=${id}&limit=12`).then(r => r.json()).then(d => {
    box.innerHTML = d.results?.length ? `<div class="similar-site-results"><b>SIMILAR SITE RESULTS · SELECT IMAGES TO COMPARE</b><div id="similarResults" class="cluster-grid">${d.results.map(r=>`<label class="result selectable-result"><input type="checkbox" value="${r.id}"><img class="result-thumb" src="/api/scenes/${r.id}/preview" alt="${r.name}"><b>${r.name}</b><small>${scoreText(r.match_score ?? r.visual_score, 'visual similarity')} · scene ${r.id}</small></label>`).join('')}</div><div class="similar-actions"><button class="mini" onclick="compareSelectedSimilar()">COMPARE SELECTED</button><span id="similarSelectionHint" class="hint">Select 2 or more images.</span></div></div>` : 'No indexed visual neighbours found.'
  }).catch(() => {
    box.textContent = 'Visual clustering unavailable.'
  })
}

// Image search status is deliberately visible while the offline model and
// structural verifier are working. The indeterminate bar avoids pretending
// that the CPU phase has a reliable percentage estimate.
async function doSearch() {
  const results = $('searchResults'),
    similar = $('clusterResults');
  if (!results) return;
  if (similar) similar.innerHTML = '';
  const imageSearch = $('referenceUpload')?.files?.[0] || $('referenceScene')?.value;
  results.innerHTML = `<div class="search-progress" role="status" aria-live="polite"><div class="search-progress-head"><b>${imageSearch ? 'MATCHING REFERENCE IMAGERY' : 'SEARCHING LOCAL INDEX'}</b><span>LOCAL · OFFLINE</span></div><div class="search-progress-track"><i></i></div><div class="search-progress-detail">${imageSearch ? 'Checking image structure and ranking verified candidates…' : 'Ranking indexed scenes by RemoteCLIP text-image similarity…'}</div></div>`;
  const upload = $('referenceUpload')?.files?.[0],
    ref = $('referenceScene')?.value;
  let response;
  try {
    if (upload && $('refineTextQuery')?.checked) throw Error('Clear text refinement to search using an uploaded image.');
    if (upload) {
      const f = new FormData();
      f.append('file', upload);
      f.append('date_from', $('from')?.value || '');
      f.append('date_to', $('to')?.value || '');
      response = await fetch('/api/search/semantic/upload?' + new URLSearchParams({
        date_from: $('from')?.value || '',
        date_to: $('to')?.value || '',
        sensor: $('sensorFilter')?.value || '',
        bbox: $('bboxFilter')?.value || ''
      }), {
        method: 'POST',
        body: f
      })
    } else {
      const p = new URLSearchParams({
        q: ref ? '' : $('query')?.value || '',
        reference_scene_id: ref || '',
        date_from: $('from')?.value || '',
        date_to: $('to')?.value || '',
        limit: '30',
        sensor: $('sensorFilter')?.value || '',
        bbox: $('bboxFilter')?.value || ''
      });
      if (!ref) p.delete('reference_scene_id');
      if ($('refineTextQuery')?.checked) {
        const ids = [...new Set((window.compareScenes || []).map(s => s.id))];
        if (ref || ids.length < 5) throw Error('For text refinement, select at least five relevant comparison images and clear the reference-image choice.');
        p.set('feedback_scene_ids', ids.join(','));
      }
      response = await fetch('/api/search/semantic?' + p)
    }
    const d = await response.json();
    if (!response.ok) {
      results.innerHTML = `<div class="hint" role="alert">${d.detail||'Local semantic index is still preparing.'}</div>`;
      return
    }
    const mode = upload ? 'Uploaded image' : d.mode === 'image-to-image' ? 'Indexed image' : 'Free-text';
    results.innerHTML = (d.results.length ? `<div class="hint">${mode} results · ${d.encoder}${d.feedback_applied?" · YOUR RELEVANCE FEEDBACK APPLIED":""} · direct matches plus available same-location timeline members. Similarity is a ranking score, not an accuracy percentage.</div>` : '<div class="hint">No indexed scene matched these filters.</div>') + (d.results || []).map(r => `<article class="result"><div class="result-visual"><img class="result-thumb" src="/api/scenes/${r.id}/preview" alt="Preview of ${r.name}" loading="lazy"><a class="image-link" href="/api/scenes/${r.id}/preview" target="_blank" rel="noopener">OPEN FULL IMAGE ↗</a></div><b>${r.name}</b><small>SCENE ID ${r.id} · ${r.kind} · ${r.width||'?'}×${r.height||'?'} · ${r.date||'date unknown'}</small><div class="score">${r.retrieval_source==='temporal_cluster'?'SAME-LOCATION TIMELINE MEMBER · linked through matched imagery':scoreText(r.match_score, r.score_type || 'visual similarity')}</div><button class="mini" onclick="pick(${r.id})">USE IN COMPARE</button><button class="mini" onclick="findSimilar(${r.id})">FIND SIMILAR SITES</button></article>`).join('');
  } catch (error) {
    results.replaceChildren();
    const message = document.createElement('p');
    message.className = 'hint';
    message.setAttribute('role', 'alert');
    message.textContent = error.message || 'Local search failed';
    results.append(message);
  }
}

// Assign the cluster workspace before filtering panels. This prevents the
// first click after startup from hiding the panel until a second navigation.
function showWorkspace(name) {
  if (name === 'clusters') {
    const cluster = document.querySelector('#clustersPanel');
    if (cluster) cluster.dataset.workspace = 'clusters';
    const index = document.querySelector('#indexBuildBtn')?.closest('section');
    if (index) index.dataset.workspace = 'clusters';
  }
  document.querySelectorAll('main > section').forEach(el => {
    const keep = el.dataset.workspace === name || (name === 'status' && el.classList.contains('metrics'));
    el.classList.toggle('workspace-hidden', !keep)
  });
  document.querySelectorAll('.nav').forEach(x => x.classList.toggle('active', x.dataset.workspace === name));
  const titles = {
    data: 'Data Library',
    discovery: 'Search & Discover',
    clusters: 'Clusters',
    compare: 'Compare Timeline',
    review: 'Review Queue',
    reports: 'Reports & Provenance',
    status: 'System Status'
  };
  const h = document.querySelector('header h1');
  if (h) h.innerHTML = `${titles[name]||'Data Library'} <span>//</span> ${name==='discovery'?'Visual retrieval':name==='clusters'?'Visual similarity':name==='compare'?'Change workspace':name==='review'?'Decision record':name==='reports'?'Audit exports':'Offline archive'}`;
  if (name === 'clusters') loadClusters();
  window.scrollTo({
    top: 0,
    behavior: 'smooth'
  });
}
