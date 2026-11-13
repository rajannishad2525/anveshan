(() => {
  const $ = id => document.getElementById(id),
    esc = clusterEscape;
  let scenes = [],
    records = [];
  const thumb = s => `<img loading="lazy" src="/api/scenes/${s.id}/preview" alt="${esc(s.name)}"><span>${esc(s.name)}<small>${esc(s.date||'Date unavailable')} · ${esc(s.crs||'CRS unavailable')} · ${esc(s.priority_reason||'')}</small></span>`;
  async function json(url, options) {
    const r = await fetch(url, options);
    const d = await r.json();
    if (!r.ok) throw Error(d.detail || 'Local service unavailable');
    return d
  }
  async function refresh() {
    $('rqStatus').textContent = 'Loading active archive and saved reviews…';
    try {
      [scenes, records] = await Promise.all([json('/api/review-queue'), json('/api/evidence-reviews')]);
      render();
      $('rqStatus').textContent = `${scenes.length} images available · ${records.length} saved reviews in this archive`
    } catch (e) {
      $('rqStatus').textContent = e.message;
      $('rpList').textContent = e.message
    }
  }

  function render() {
    const selected = new Set((window.compareScenes || []).map(s => s.id));
    for (const id of ['beforeId', 'afterId'])
      if (Number($(id)?.value)) selected.add(Number($(id).value));
    $('rqImages').innerHTML = scenes.map(s => `<label class="rqPick"><input type="checkbox" value="${s.id}" ${selected.has(s.id)?'checked':''}>${thumb(s)}</label>`).join('') || '<p>Import imagery in Data Library to start a review.</p>';
    $('rpList').innerHTML = records.map(r => `<article class="rpRecord"><h3>${esc(r.decision.toUpperCase())}</h3><small>${esc(r.timestamp)} · ${r.scenes.length} observations</small><p>${esc(r.note)}</p><div class="rpThumbs">${r.scenes.map(thumb).join('')}</div><details><summary>Source provenance</summary>${r.scenes.map(s=>`<p>${esc(s.name)}<br>Source: ${esc(s.path)}<br>SHA-256: ${esc(s.sha256)}<br>Imported: ${esc(s.imported_at)}<br>Date/period: ${esc(s.date||'Unavailable')}</p>`).join('')}</details><p class="rqCaveat">Analyst decision · automated change accuracy has not been established.</p></article>`).join('') || '<p>No saved evidence reviews for this archive. Save a decision in Review Queue first.</p>';
    $('rpCount').textContent = `${records.length} review records · ${records.filter(r=>r.decision==='accepted').length} accepted · ${records.filter(r=>r.decision==='rejected').length} rejected · ${records.filter(r=>r.decision==='needs-review').length} need review`;
  }
  async function save() {
    const ids = [...document.querySelectorAll('#rqImages input:checked')].map(x => Number(x.value));
    if (!ids.length || !$('rqNote').value.trim()) {
      $('rqStatus').textContent = 'Select images and enter your reason before saving.';
      return
    }
    $('rqSave').disabled = true;
    try {
      await json('/api/evidence-reviews', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          scene_ids: ids,
          decision: $('rqDecision').value,
          note: $('rqNote').value
        })
      });
      await refresh();
      $('rqStatus').textContent = 'Decision saved with source snapshots. See Reports & Provenance.';
      $('rqNote').value = ''
    } catch (e) {
      $('rqStatus').textContent = e.message
    } finally {
      $('rqSave').disabled = false
    }
  }
  async function download() {
    try {
      const data = await json('/api/evidence-reviews/export');
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {
        type: 'application/json'
      }));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'anveshan-reviewed-evidence.json';
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      $('rpCount').textContent = e.message
    }
  }
  window.addEventListener('load', () => {
    document.querySelectorAll('main > section[data-workspace="review"],main > section[data-workspace="reports"]').forEach(s => {
      s.dataset.workspace = 'legacy-review';
      s.classList.add('workspace-hidden')
    });
    const footer = document.querySelector('main > footer');
    const queue = document.createElement('section');
    queue.className = 'panel workspace workspace-hidden';
    queue.dataset.workspace = 'review';
    queue.id = 'reviewQueuePanel';
    queue.innerHTML = '<div class="panel-head"><div><div class="eyebrow">05 / HUMAN REVIEW</div><h3>Review selected observations</h3></div><button id="rqRefresh">REFRESH QUEUE</button></div><div class="rqBody"><p>Images selected for comparison are checked below. Verify the observations, then record your decision and reason.</p><input id="rqFilter" placeholder="Filter images by filename"><div id="rqImages" class="rqGrid"></div><label>Decision <select id="rqDecision"><option value="needs-review">Needs further review</option><option value="accepted">Accept candidate</option><option value="rejected">Reject candidate</option></select></label><label>Reason / evidence notes<textarea id="rqNote" rows="3" placeholder="Describe the observations, periods, and uncertainty behind your decision."></textarea></label><button id="rqSave">SAVE EVIDENCE REVIEW</button><p id="rqStatus" role="status"></p></div>';
    footer.before(queue);
    const reports = document.createElement('section');
    reports.className = 'panel workspace workspace-hidden';
    reports.dataset.workspace = 'reports';
    reports.id = 'reviewReportsPanel';
    reports.innerHTML = '<div class="panel-head"><div><div class="eyebrow">06 / REPORTS & PROVENANCE</div><h3>Reviewed evidence and source history</h3></div><button id="rpRefresh">REFRESH REPORTS</button></div><div class="rqBody"><p id="rpCount" role="status"></p><button id="rpExport">EXPORT REVIEW + PROVENANCE JSON</button><button id="rpPrint">PRINT / SAVE PDF</button><div id="rpList"></div></div>';
    footer.before(reports);
    $('rqRefresh').onclick = refresh;
    $('rpRefresh').onclick = refresh;
    $('rqSave').onclick = save;
    $('rpExport').onclick = download;
    $('rpPrint').onclick = () => {
      document.body.classList.add('printing-reviews');
      window.print();
      document.body.classList.remove('printing-reviews')
    };
    $('rqFilter').oninput = () => document.querySelectorAll('.rqPick').forEach(n => n.hidden = !n.textContent.toLowerCase().includes($('rqFilter').value.toLowerCase()));
    document.querySelectorAll('.nav').forEach(n => {
      if (['review', 'reports'].includes(n.dataset.workspace)) n.addEventListener('click', refresh)
    });
  });
})();
