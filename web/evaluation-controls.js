window.addEventListener('load', () => {
  const panel = document.getElementById('reviewReportsPanel');
  if (!panel) return;
  const area = document.createElement('div');
  area.className = 'rqBody';
  area.innerHTML = `<h3>Offline evaluation & performance</h3>
    <p>Measure this archive separately from operational review decisions. Accuracy requires independent human labels.</p>
    <button id="measureArchive">MEASURE CURRENT ARCHIVE</button>
    <p id="measurementStatus" role="status"></p><div id="measurementResults"></div>
    <button id="exportMeasurement" hidden>DOWNLOAD BENCHMARK JSON + MARKDOWN</button>
    <details><summary>Evaluate search relevance with two independent reviewers</summary>
      <p>Choose 10–15 queries before judging. Freeze the results, then ask two different people to mark relevance independently. Unresolved disagreements do not produce a combined accuracy score.</p>
      <label>Evaluation queries — one per line<textarea id="evaluationQueries" rows="10">river
urban buildings
agricultural fields
roads
water bodies
forest
open ground
industrial buildings
bridges
residential area</textarea></label>
      <button id="freezeEvaluation">FREEZE QUERY RESULTS</button><p id="evaluationStatus" role="status"></p>
      <label>Reviewer A <input id="reviewerA" placeholder="First reviewer name"></label>
      <label>Reviewer B <input id="reviewerB" placeholder="Second reviewer name"></label>
      <div id="evaluationPool"></div><button id="scoreEvaluation" hidden>CALCULATE RELEVANCE METRICS</button>
      <button id="exportEvaluation" hidden>EXPORT FROZEN EVALUATION</button>
    </details>`;
  panel.append(area);
  const el = id => document.getElementById(id);
  let measurement, pool, evaluation;
  const download = (name, text, type) => {
    const url = URL.createObjectURL(new Blob([text], {
      type
    }));
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  async function post(url, body) {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(body || {})
    });
    const data = await response.json();
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Check the submitted fields and try again.');
    return data;
  }

  function loading(target, label) {
    target.replaceChildren(document.createTextNode(label));
    const bar = document.createElement('progress');
    bar.setAttribute('aria-label', label);
    target.append(bar);
  }
  el('measureArchive').onclick = async () => {
    el('measureArchive').disabled = true;
    loading(el('measurementStatus'), 'Measuring offline query latency…');
    try {
      measurement = await post('/api/benchmark/current');
      el('measurementStatus').textContent = `${measurement.scene_count} scenes · ${measurement.indexed_representatives} indexed representatives. Warm queries: median ${(measurement.warm_query_p50_seconds*1000).toFixed(0)} ms; p95 ${(measurement.warm_query_p95_seconds*1000).toFixed(0)} ms. Build: ${measurement.build_seconds == null ? 'not measured' : measurement.build_seconds+' seconds'}. ${measurement.note}`;
      el('exportMeasurement').hidden = false;
    } catch (error) {
      el('measurementStatus').textContent = error.message;
    } finally {
      el('measureArchive').disabled = false;
    }
  };
  el('exportMeasurement').onclick = () => {
    download('anveshan-benchmark.json', JSON.stringify(measurement, null, 2), 'application/json');
    download('anveshan-benchmark.md', '# Measured archive benchmark\n\n' + Object.entries(measurement).map(([k, v]) => `- ${k}: ${v == null ? 'not measured' : v}`).join('\n'), 'text/markdown');
  };
  el('freezeEvaluation').onclick = async () => {
    el('freezeEvaluation').disabled = true;
    loading(el('evaluationStatus'), 'Freezing offline retrieval results…');
    try {
      pool = await post('/api/evaluation/retrieval/freeze', {
        queries: el('evaluationQueries').value.split('\n')
      });
      evaluation = null;
      el('evaluationPool').replaceChildren();
      pool.queries.forEach((query, i) => {
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = `${i+1}. ${query.query} · ${query.results.length} results`;
        details.append(summary);
        query.results.forEach(row => {
          const card = document.createElement('div');
          card.className = 'evaluation-row';
          const img = document.createElement('img');
          img.src = `/api/scenes/${row.scene_id}/preview`;
          img.alt = row.name;
          img.width = 128;
          img.loading = 'lazy';
          card.append(img);
          const text = document.createElement('span');
          text.textContent = `Rank ${row.rank} · ${row.name}`;
          card.append(text);
          ['a', 'b'].forEach(judge => {
            const label = document.createElement('label');
            label.textContent = `Reviewer ${judge.toUpperCase()} `;
            const select = document.createElement('select');
            select.dataset.query = i;
            select.dataset.scene = row.scene_id;
            select.dataset.judge = judge;
            select.add(new Option('Unjudged', ''));
            select.add(new Option('Relevant', 'true'));
            select.add(new Option('Not relevant', 'false'));
            label.append(select);
            card.append(label);
          });
          details.append(card);
        });
        el('evaluationPool').append(details);
      });
      el('evaluationStatus').textContent = 'Results frozen. Both reviewers must judge every returned image.';
      el('scoreEvaluation').hidden = false;
      el('exportEvaluation').hidden = false;
    } catch (error) {
      el('evaluationStatus').textContent = error.message;
    } finally {
      el('freezeEvaluation').disabled = false;
    }
  };
  const judgmentBody = () => ({
    freeze_id: pool.freeze_id,
    reviewer_a: el('reviewerA').value.trim(),
    reviewer_b: el('reviewerB').value.trim(),
    judgments: pool.queries.flatMap((q, i) => q.results.map(row => {
      const value = judge => el('evaluationPool').querySelector(`select[data-query="${i}"][data-scene="${row.scene_id}"][data-judge="${judge}"]`).value;
      return {
        query_index: i,
        scene_id: row.scene_id,
        judge_a: value('a') === '' ? null : value('a') === 'true',
        judge_b: value('b') === '' ? null : value('b') === 'true'
      };
    }))
  });
  el('scoreEvaluation').onclick = async () => {
    const body = judgmentBody();
    if (body.judgments.some(j => j.judge_a == null || j.judge_b == null)) {
      el('evaluationStatus').textContent = 'Some images remain unjudged. Ask both reviewers to finish their labels.';
      return;
    }
    el('scoreEvaluation').disabled = true;
    try {
      evaluation = await post('/api/evaluation/retrieval/score', body);
      el('evaluationStatus').textContent = `${evaluation.status}. Disagreements: ${evaluation.disagreements}. P@5: ${evaluation.precision_at_5??'pending'} · P@10: ${evaluation.precision_at_10??'pending'} · MRR: ${evaluation.mrr??'pending'} · Cohen κ: ${evaluation.cohen_kappa??'undefined'}. ${evaluation.note}`;
    } catch (error) {
      el('evaluationStatus').textContent = error.message;
    } finally {
      el('scoreEvaluation').disabled = false;
    }
  };
  el('exportEvaluation').onclick = () => download('anveshan-frozen-evaluation.json', JSON.stringify({
    pool,
    judgments: judgmentBody(),
    metrics: evaluation
  }, null, 2), 'application/json');
});
