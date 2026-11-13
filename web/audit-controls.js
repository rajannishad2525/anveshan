window.addEventListener('load', () => {
  const feedback = document.createElement('label');
  feedback.className = 'hint';
  feedback.innerHTML = '<input type="checkbox" id="refineTextQuery"> Refine this text query using my selected comparison images (minimum 5). I judge these images relevant to this query.';
  document.getElementById('searchResults').before(feedback);
  const filters = document.createElement('p');
  filters.className = 'hint';
  filters.textContent = 'Filters: All sensors shows every ready scene. Pick a sensor to restrict results. AOI uses WGS84 bbox format: west,south,east,north, for example 77.46,28.435,77.515,28.483.';
  document.getElementById('searchResults').before(filters);
  async function refreshSensors() {
    const select = document.getElementById('sensorFilter');
    try {
      const response = await fetch('/api/archive/sensors');
      if (!response.ok) return;
      const data = await response.json();
      const previous = select.value;
      select.replaceChildren(new Option('All sensors', ''));
      data.sensors.forEach(sensor => select.add(new Option(sensor, sensor)));
      if (data.sensors.includes(previous)) select.value = previous;
      select.title = `${data.missing} observations have no supplied sensor metadata`;
    } catch (_) {
      /* Keep the existing filter if the server is restarting. */ }
  }
  refreshSensors();
  document.querySelectorAll('.nav').forEach(n => n.addEventListener('click', refreshSensors));
  const button = document.getElementById('tileBuild');
  const status = document.getElementById('tileStatus');
  button.onclick = async () => {
    button.disabled = true;
    status.textContent = 'Preparing local tile job…';
    try {
      const response = await fetch('/api/tiles/build', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          tile_size: 512
        })
      });
      const job = await response.json();
      if (!response.ok) throw new Error(job.detail || 'Tiling could not start');
      document.getElementById('progress').classList.remove('hidden');
      watch(job.id);
      status.textContent = 'Tile progress appears below. Build the local index when complete.';
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  };
});

window.checkClusterReadiness = async (button, key) => {
  const target = button.nextElementSibling;
  button.disabled = true;
  try {
    const response = await fetch('/api/clusters?limit=500');
    if (!response.ok) throw Error('Cluster data unavailable');
    const group = (await response.json()).find(g => g.key === key);
    if (!group) throw Error('Archive changed; reopen the cluster');
    const bar = document.createElement('progress');
    bar.max = group.scenes.length - 1;
    bar.value = 0;
    const text = document.createElement('p');
    target.replaceChildren(text, bar);
    for (let i = 1; i < group.scenes.length; i++) {
      text.textContent = `Checking pair ${i} of ${group.scenes.length-1}…`;
      const a = group.scenes[i - 1],
        b = group.scenes[i];
      const r = await fetch(`/api/compare/readiness?before=${a.id}&after=${b.id}`);
      const data = await r.json();
      if (!r.ok) throw Error(data.detail || 'Readiness unavailable');
      const badge = document.createElement('p');
      badge.textContent = `${a.period_label||a.date||'Unknown date'} → ${b.period_label||b.date||'Unknown date'}: ${data.analysable?'Ready for visual screening':data.reason}`;
      target.append(badge);
      bar.value = i;
    }
    text.textContent = 'Checks complete. Readiness is not change-detection accuracy.';
  } catch (error) {
    target.textContent = error.message;
  } finally {
    button.disabled = false;
  }
};
