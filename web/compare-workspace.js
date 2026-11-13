// Visual selection is the operator interface; numeric IDs remain internal.
(() => {
  const el = id => document.getElementById(id);
  const esc = clusterEscape;
  let selected = [],
    busy = false;
  const date = s => s.period_label || s.date || 'Date unavailable';
  const card = s => `<figure class="timeline-image"><img src="/api/scenes/${s.id}/preview" alt="${esc(s.name)}"><figcaption>${esc(date(s))} · ${esc(s.name)}</figcaption></figure>`;
  async function selection() {
    const ids = [...new Set((window.compareScenes || []).map(s => s.id))];
    if (!ids.length)[el('beforeId'), el('afterId')].forEach(x => {
      if (Number(x?.value) && !ids.includes(Number(x.value))) ids.push(Number(x.value))
    });
    selected = await Promise.all(ids.map(async id => {
      const r = await fetch('/api/scenes/' + id);
      if (!r.ok) throw Error('A selected image is no longer in the archive. Select images again.');
      return r.json()
    }));
    selected.sort((a, b) => date(a).localeCompare(date(b), undefined, {
      numeric: true
    }));
    return selected;
  }
  async function openCompareTool() {
    try {
      await selection();
      render();
      if (selected.length < 2) throw Error('Select at least two images first.');
      if (typeof window.openImageInspector !== 'function') throw Error('Image comparison tool is not loaded.');
      window.openImageInspector(selected);
      el('compareStatus').textContent = `${selected.length} selected observations opened in the comparison tool.`
    } catch (e) {
      el('compareStatus').textContent = e.message
    }
  }

  function render() {
    el('compareView').innerHTML = selected.map(card).join('');
    el('compareStatus').textContent = `${selected.length} selected observations · ordered by supplied date/period. Overlapping periods do not establish an exact capture order.`
  }
  const pct = value => value === null || value === undefined ? 'n/a' : `${Math.round(Number(value) * 1000) / 10}%`;
  function falseAlarmCard(data) {
    const flags = data.flags?.length ? data.flags : ['No strong nuisance signal detected in the screening thumbnail'];
    const metrics = data.signals || {};
    const comparison = data.comparison || {};
    return `<article class="false-alarm-panel ${data.quality_gate==='pass'?'pass':'review'}"><div class="false-alarm-head"><b>FALSE ALARM SUPPRESSION</b><span>${esc(data.quality_gate||'review required')}</span></div><div class="false-alarm-metrics"><span>raw change <b>${pct(comparison.raw_changed_pixel_ratio)}</b></span><span>after suppression <b>${pct(comparison.adjusted_changed_pixel_ratio)}</b></span><span>suppressed <b>${pct(comparison.suppressed_pixel_fraction)}</b></span></div><ul>${flags.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><small>Bright/cloud-like ${pct(metrics.bright_low_chroma_fraction)} · haze-like ${pct(metrics.haze_like_fraction)} · shadow-like ${pct(metrics.dark_shadow_fraction)} · illumination shift ${pct(metrics.mean_luminance_shift)}. ${esc(data.caveat||'')}</small></article>`
  }
  async function renderFalseAlarm(a, b, target) {
    const panel = document.createElement('div');
    panel.className = 'false-alarm-slot';
    panel.innerHTML = '<article class="false-alarm-panel"><div class="false-alarm-head"><b>FALSE ALARM SUPPRESSION</b><span>checking</span></div><div class="false-alarm-scan"><i></i></div></article>';
    target.append(panel);
    try {
      const r = await fetch(`/api/false-alarm/pair?before=${a.id}&after=${b.id}`);
      const d = await r.json();
      panel.innerHTML = r.ok ? falseAlarmCard(d) : `<article class="false-alarm-panel review"><div class="false-alarm-head"><b>FALSE ALARM SUPPRESSION</b><span>review required</span></div><p>${esc(d.detail||'Quality screening unavailable')}</p></article>`
    } catch (e) {
      panel.innerHTML = `<article class="false-alarm-panel review"><div class="false-alarm-head"><b>FALSE ALARM SUPPRESSION</b><span>offline check failed</span></div><p>${esc(e.message||'Quality screening unavailable')}</p></article>`
    }
  }
  function llmBriefCard(d) {
    const f = d.facts || {};
    const warnings = (f.warnings || []).length ? (f.warnings || []).slice(0, 4).map(x => `<li>${esc(x)}</li>`).join('') : '<li>No strong nuisance warning confirmed by local screening.</li>';
    return `<article class="llm-brief-panel"><div class="false-alarm-head"><b>ANALYST BRIEF</b><span>${esc(d.llm?.available?'local llm wording':'template · no llm')}</span></div><p>${esc(d.brief || 'Brief unavailable')}</p><div class="llm-facts"><span>Date A <b>${esc(f.date_a || 'n/a')}</b></span><span>Date B <b>${esc(f.date_b || 'n/a')}</b></span><span>Changed pixels <b>${esc(String(f.changed_pixel_ratio_percent ?? 'n/a'))}%</b></span><span>Candidate regions <b>${esc(String(f.regions ?? 'n/a'))}</b></span><span>Cloud / haze <b>${esc(f.cloud || 'n/a')}</b></span><span>Alignment <b>${esc(f.alignment || 'n/a')}</b></span></div><ul>${warnings}</ul><small>${esc(d.caveat || '')}</small></article>`
  }
  async function renderLlmBrief(a, b, target) {
    const panel = document.createElement('div');
    panel.className = 'false-alarm-slot';
    panel.innerHTML = '<article class="llm-brief-panel"><div class="false-alarm-head"><b>ANALYST BRIEF</b><span>writing</span></div><div class="false-alarm-scan"><i></i></div></article>';
    target.append(panel);
    try {
      const r = await fetch(`/api/llm/compare-report?before=${a.id}&after=${b.id}`);
      const d = await r.json();
      panel.innerHTML = r.ok ? llmBriefCard(d) : `<article class="llm-brief-panel"><div class="false-alarm-head"><b>ANALYST BRIEF</b><span>review required</span></div><p>${esc(d.detail||'Brief unavailable')}</p></article>`
    } catch (e) {
      panel.innerHTML = `<article class="llm-brief-panel"><div class="false-alarm-head"><b>ANALYST BRIEF</b><span>offline fallback failed</span></div><p>${esc(e.message||'Brief unavailable')}</p></article>`
    }
  }
  async function report(a, b, target) {
    target.innerHTML = card(a) + card(b) + '<p>Checking source alignment and visual differences…</p>';
    const r = await fetch(`/api/change/registered?before=${a.id}&after=${b.id}`),
      d = await r.json();
    const p = document.createElement('p');
    p.textContent = r.ok ? `${date(a)} → ${date(b)}: ${Math.round(d.adjusted_changed_pixel_ratio*100)}% of usable overlap has candidate visual differences after registration and normalization. ${d.region_count} candidate regions${d.regions_listed < d.region_count ? ` (largest ${d.regions_listed} drawn)` : ''}. ${d.note}` : `${date(a)} → ${date(b)}: Analysis unavailable. ${d.detail||'Source imagery could not be verified'}. Inspect the images above; no change conclusion has been generated.`;
    target.lastElementChild.replaceWith(p);
    if (r.ok && d.regions?.length) {
      const figure = document.createElement('div');
      figure.style.cssText = 'position:relative;max-width:512px';
      const img = document.createElement('img');
      img.src = '/api/scenes/' + a.id + '/preview';
      img.style.cssText = 'width:100%;display:block';
      figure.append(img);
      d.regions.forEach(region => {
        const [x, y, x2, y2] = region.bbox_pixels;
        const box = document.createElement('span');
        box.style.cssText = `position:absolute;border:1px solid #ffb454;left:${x/d.analysis_size.width*100}%;top:${y/d.analysis_size.height*100}%;width:${(x2-x)/d.analysis_size.width*100}%;height:${(y2-y)/d.analysis_size.height*100}%`;
        figure.append(box)
      });
      target.append(figure);
    }
    await renderFalseAlarm(a, b, target);
    await renderLlmBrief(a, b, target);
  }
  async function allReports() {
    if (busy) return;
    busy = true;
    el('compareBtn').disabled = true;
    try {
      await selection();
      render();
      if (selected.length < 2) throw Error('Select at least two images from Search & Discover.');
      el('timelineView').innerHTML = '';
      for (let i = 1; i < selected.length; i++) {
        el('compareStatus').textContent = `Comparing observations ${i} / ${selected.length-1}…`;
        const box = document.createElement('article');
        box.className = 'timeline-report';
        el('timelineView').append(box);
        await report(selected[i - 1], selected[i], box)
      }
      el('compareStatus').textContent = `${selected.length-1} pair reports complete. Review each result and any alignment warnings.`;
    } catch (e) {
      el('compareStatus').textContent = e.message
    } finally {
      busy = false;
      el('compareBtn').disabled = false
    }
  }
  async function timeline() {
    try {
      await selection();
      render();
      const onsetResponse = await fetch('/api/timeline/onset', {
        method: 'POST',
        headers: {
          'content-type': 'application/json'
        },
        body: JSON.stringify({
          scene_ids: selected.map(s => s.id)
        })
      });
      const onset = await onsetResponse.json();
      el('compareStatus').textContent = onsetResponse.ok ? `${onset.status}. First supporting observation: ${onset.first_supporting_observation?.date||'unavailable'}. Last usable no-change: ${onset.last_usable_no_change?.date||'unavailable'}. Gaps: ${onset.gaps.length}. ${onset.note}` : (onset.detail || 'Timeline unavailable');
      if (onset.year_resolution) {
        const y = onset.year_resolution;
        el('compareStatus').textContent += ` Year-resolution screening: first candidate ${y.first_supporting_observation?.year||'unavailable'}; prior no-change ${y.last_usable_no_change?.year||'unavailable'}. ${y.note}`;
      }
      el('timelineView').innerHTML = '<p>Observation timeline: select a pair below to inspect it. Dates are supplied metadata.</p>';
      for (let i = 1; i < selected.length; i++) {
        const a = selected[i - 1],
          b = selected[i],
          button = document.createElement('button');
        button.textContent = `${date(a)} → ${date(b)}`;
        button.onclick = () => choosePair(a, b);
        el('timelineView').append(button)
      }
    } catch (e) {
      el('compareStatus').textContent = e.message
    }
  }
  async function choosePair(a, b) {
    el('beforeId').value = a.id;
    el('afterId').value = b.id;
    el('compareView').innerHTML = card(a) + card(b);
    el('compareStatus').textContent = `Selected pair: ${date(a)} → ${date(b)}`;
    el('timelineView').innerHTML = '';
    const box = document.createElement('article');
    box.className = 'timeline-report';
    el('timelineView').append(box);
    try {
      await report(a, b, box)
    } catch (e) {
      box.textContent = e.message
    }
  }
  async function pairs() {
    if (busy) return;
    busy = true;
    el('pairsBtn').disabled = true;
    try {
      await selection();
      el('pairsView').innerHTML = '';
      let count = 0;
      for (let i = 0; i < selected.length; i++)
        for (let j = i + 1; j < selected.length; j++) {
          el('compareStatus').textContent = `Verifying suggested pair ${i+1} / ${j+1}…`;
          const a = selected[i],
            b = selected[j],
            r = await fetch(`/api/compare/readiness?before=${a.id}&after=${b.id}`);
          if (!r.ok) continue;
          const d = await r.json();
          if (!d.analysable) continue;
          const button = document.createElement('button');
          button.className = 'verified-pair';
          button.innerHTML = card(a) + card(b) + `<span>${esc(date(a))} → ${esc(date(b))} · ready for screening</span>`;
          button.onclick = () => choosePair(a, b);
          el('pairsView').append(button);
          count++
        }
      el('compareStatus').textContent = `${count} analysable pair suggestions among selected images.`
    } catch (e) {
      el('compareStatus').textContent = e.message
    } finally {
      busy = false;
      el('pairsBtn').disabled = false
    }
  }
  window.addEventListener('load', () => {
    el('beforeId').type = 'hidden';
    el('afterId').type = 'hidden';
    if (!el('inspectCompareBtn')) {
      const button = document.createElement('button');
      button.id = 'inspectCompareBtn';
      button.type = 'button';
      button.textContent = 'OPEN COMPARE TOOL';
      button.onclick = openCompareTool;
      el('pairsBtn').after(button);
    }
    el('compareBtn').onclick = allReports;
    el('timelineBtn').onclick = timeline;
    el('pairsBtn').onclick = pairs;
    el('footprintBtn').hidden = true;
    el('footprintView').hidden = true;
    el('compareStatus').textContent = 'Select imagery from Search & Discover. Compare scenes reviews every consecutive observation in date order.'
  });
})();
