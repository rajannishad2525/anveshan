/* Comparison viewer: display modes plus the analyst tools that read pixels.
 *
 * Display modes (side, overlay, swipe, spy, blink, timeline) show the previews.
 * Analysis modes (composite, difference) and the panel tools (histogram,
 * scatter, profile) read pixel values, and every one of them works on a single
 * shared reference grid so that two dates are always compared cell for cell.
 *
 * The arithmetic lives in image-analysis.js; this file is the viewer around it.
 */
(() => {
  'use strict';

  /* One grid for display and for analysis. Capped to match the server's own
   * analysis convention (_analysis_image max_side=1024) and so that measurement
   * and profiling share the coordinate space the analyst is looking at. */
  const REFERENCE_MAX_SIDE = 1024;
  const PROFILE_SAMPLES = 240;
  const SCATTER_BINS = 64;

  let modal, canvas, ctx, panel, panelCtx,
    images = [],
    scenes = [],
    mode = 'side',
    tool = 'none',
    a = 0,
    b = 1,
    c = 2,
    frame = 0,
    zoom = 1,
    pan = {
      x: 0,
      y: 0
    },
    drag = null,
    timer = null,
    observer,
    pointer = null,
    /* Rebuilt whenever the pair, the stretch or the grid changes. */
    grid = null,
    rendered = {},
    planes = {},
    composite = null,
    diff = null,
    heat = null,
    heatThreshold = null,
    heatCeiling = null,
    groundScale = {},
    view = null,
    measurePoints = [],
    profileLine = null,
    profileDrag = null;

  const $ = id => document.getElementById(id);
  const MODES = ['side', 'overlay', 'swipe', 'spy', 'blink', 'timeline', 'composite', 'difference'];
  const MODE_LABELS = {
    side: 'SIDE BY SIDE',
    overlay: 'OVERLAY',
    swipe: 'SWIPE',
    spy: 'SPY',
    blink: 'BLINK',
    timeline: 'TIMELINE',
    composite: 'DATE COMPOSITE',
    difference: 'DIFFERENCE'
  };
  const PANEL_TOOLS = ['histogram', 'scatter', 'profile'];

  function stop() {
    clearInterval(timer);
    timer = null;
    if ($('ivPlay')) $('ivPlay').textContent = 'PLAY';
  }

  function label(i) {
    const s = scenes[i];
    return s ? `${s.period_label||s.date||'Date unavailable'} · ${s.name}` : '';
  }

  function shortLabel(i) {
    const s = scenes[i];
    return s ? (s.period_label || s.date || 'undated') : '—';
  }

  /* ------------------------------------------------------------------ *
   * Reference grid and cached pixel products
   * ------------------------------------------------------------------ */

  function activeIndices() {
    const list = [a, b];
    if (mode === 'composite' && scenes.length > 2) list.push(c);
    return [...new Set(list)].filter(i => images[i]);
  }

  function stretchSettings() {
    const method = $('ivStretch') ? $('ivStretch').value : 'none';
    const gamma = $('ivGamma') ? Number($('ivGamma').value) / 100 : 1;
    return {
      method: method,
      gamma: gamma
    };
  }

  /** Recompute every cached pixel product. Cheap enough to call on any change. */
  function rebuild() {
    const base = images[a] || images[b];
    if (!base) {
      grid = null;
      return;
    }
    const longest = Math.max(base.naturalWidth, base.naturalHeight) || 1;
    const factor = Math.min(1, REFERENCE_MAX_SIDE / longest);
    grid = {
      w: Math.max(1, Math.round(base.naturalWidth * factor)),
      h: Math.max(1, Math.round(base.naturalHeight * factor))
    };

    const settings = stretchSettings();
    rendered = {};
    planes = {};
    let description = 'no stretch';
    for (const i of activeIndices()) {
      const raw = window.ImageAnalysis.toImageData(images[i], grid.w, grid.h);
      let shown = raw;
      if (settings.method !== 'none') {
        const built = window.ImageAnalysis.stretchLUTs(raw, settings.method, settings.gamma);
        shown = window.ImageAnalysis.applyLUTs(raw, built.luts);
        description = built.description;
      }
      const surface = document.createElement('canvas');
      surface.width = grid.w;
      surface.height = grid.h;
      surface.getContext('2d').putImageData(shown, 0, 0);
      rendered[i] = surface;
      planes[i] = window.ImageAnalysis.luminance(shown);
    }
    if ($('ivStretchNote')) {
      $('ivStretchNote').textContent = settings.method === 'none' ? '' :
        'Stretch: ' + description + ' · computed per image, so it aids the eye but does not preserve radiometric comparability between dates.';
    }

    composite = null;
    diff = null;
    heat = null;
    heatThreshold = null;
    heatCeiling = null;

    if (planes[a] && planes[b]) {
      diff = window.ImageAnalysis.difference(planes[a], planes[b]);
    }
    if (mode === 'composite') {
      const order = scenes.length > 2 ? [a, b, c] : [a, b];
      const list = order.map(i => planes[i]).filter(Boolean);
      if (list.length >= 2) {
        const data = window.ImageAnalysis.temporalComposite(list, grid.w, grid.h);
        composite = document.createElement('canvas');
        composite.width = grid.w;
        composite.height = grid.h;
        composite.getContext('2d').putImageData(data, 0, 0);
      }
    }
    ensureHeat();
  }

  function ensureHeat() {
    if (mode !== 'difference' || !diff) return;
    const threshold = Number($('ivThreshold').value) / 100;
    if (heat && heatThreshold === threshold) return;
    const built = window.ImageAnalysis.heatmap(diff, threshold);
    heat = document.createElement('canvas');
    heat.width = diff.width;
    heat.height = diff.height;
    heat.getContext('2d').putImageData(built.data, 0, 0);
    heatThreshold = threshold;
    heatCeiling = built.ceiling;
  }

  function surfaceFor(i) {
    return rendered[i] || images[i] || null;
  }

  /* ------------------------------------------------------------------ *
   * Canvas geometry
   * ------------------------------------------------------------------ */

  /** Where the reference grid lands on the canvas, for the current view. */
  function layout(w, h, x, width) {
    if (!grid) return null;
    const scale = Math.min(width / grid.w, (h - 42) / grid.h) * zoom;
    return {
      scale: scale,
      left: x + width / 2 - grid.w * scale / 2 + pan.x,
      top: h / 2 - grid.h * scale / 2 + pan.y,
      width: grid.w * scale,
      height: grid.h * scale
    };
  }

  function canvasToImage(px, py) {
    if (!view) return null;
    return {
      x: (px - view.left) / view.scale,
      y: (py - view.top) / view.scale
    };
  }

  function imageToCanvas(ix, iy) {
    if (!view) return null;
    return {
      x: view.left + ix * view.scale,
      y: view.top + iy * view.scale
    };
  }

  function pointerPosition(e) {
    const r = canvas.getBoundingClientRect();
    return {
      x: e.clientX - r.left,
      y: e.clientY - r.top
    };
  }

  /* ------------------------------------------------------------------ *
   * Drawing
   * ------------------------------------------------------------------ */

  function drawSurface(i, x, width, w, h, alpha) {
    const surface = surfaceFor(i);
    if (!surface) return;
    const box = layout(w, h, x, width);
    if (!box) return;
    ctx.save();
    ctx.beginPath();
    ctx.rect(x, 0, width, h);
    ctx.clip();
    ctx.globalAlpha = alpha === undefined ? 1 : alpha;
    ctx.drawImage(surface, box.left, box.top, box.width, box.height);
    ctx.restore();
  }

  function draw() {
    if (!canvas) return;
    const w = canvas.clientWidth,
      h = canvas.clientHeight;
    if (!w || !h) return;
    canvas.width = w * devicePixelRatio;
    canvas.height = h * devicePixelRatio;
    ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    ctx.fillStyle = '#080e0c';
    ctx.fillRect(0, 0, w, h);

    view = layout(w, h, 0, w);
    const blend = Number($('ivBlend').value) / 100;

    if (mode === 'side') {
      drawSurface(a, 0, w / 2, w, h);
      drawSurface(b, w / 2, w / 2, w, h);
      ctx.strokeStyle = '#78974e';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(w / 2, 0);
      ctx.lineTo(w / 2, h);
      ctx.stroke();
      /* Side-by-side has two panes, so a single image-space cursor mapping
       * would be wrong. Pixel tools are disabled for it. */
      view = null;
    } else if (mode === 'overlay') {
      drawSurface(a, 0, w, w, h);
      drawSurface(b, 0, w, w, h, blend);
    } else if (mode === 'swipe') {
      /* The divider is a fixed reference line down the middle of the viewport.
       * It never moves: the analyst drags the imagery underneath it. */
      const split = w / 2;
      drawSurface(a, 0, w, w, h);
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, split, h);
      ctx.clip();
      drawSurface(b, 0, w, w, h);
      ctx.restore();
      ctx.strokeStyle = '#c6ed70';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(split, 0);
      ctx.lineTo(split, h);
      ctx.stroke();
    } else if (mode === 'spy') {
      drawSurface(a, 0, w, w, h);
      const radius = Number($('ivSpyRadius').value);
      const at = pointer || {
        x: w / 2,
        y: h / 2
      };
      ctx.save();
      ctx.beginPath();
      ctx.arc(at.x, at.y, radius, 0, Math.PI * 2);
      ctx.clip();
      drawSurface(b, 0, w, w, h);
      ctx.restore();
      ctx.strokeStyle = '#c6ed70';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(at.x, at.y, radius, 0, Math.PI * 2);
      ctx.stroke();
    } else if (mode === 'composite') {
      if (composite) {
        const box = layout(w, h, 0, w);
        ctx.drawImage(composite, box.left, box.top, box.width, box.height);
      }
    } else if (mode === 'difference') {
      drawSurface(a, 0, w, w, h);
      ensureHeat();
      if (heat) {
        const box = layout(w, h, 0, w);
        ctx.globalAlpha = Number($('ivHeatOpacity').value) / 100;
        ctx.drawImage(heat, box.left, box.top, box.width, box.height);
        ctx.globalAlpha = 1;
      }
    } else {
      drawSurface(frame, 0, w, w, h);
    }

    drawMeasurement();
    drawProfileLine();
    updateStatus();
    drawPanel();
    $('ivZoomText').textContent = zoom.toFixed(1) + '×';
  }

  function drawMeasurement() {
    if (tool !== 'measure' || !measurePoints.length || !view) return;
    const pts = measurePoints.map(p => imageToCanvas(p.x, p.y));
    ctx.save();
    ctx.strokeStyle = '#ffd166';
    ctx.fillStyle = 'rgba(255,209,102,0.18)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    pts.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y));
    if (pts.length > 2) {
      ctx.closePath();
      ctx.fill();
    }
    ctx.stroke();
    ctx.fillStyle = '#ffd166';
    pts.forEach(p => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.restore();
  }

  function drawProfileLine() {
    if (tool !== 'profile' || !profileLine || !view) return;
    const p0 = imageToCanvas(profileLine.x0, profileLine.y0);
    const p1 = imageToCanvas(profileLine.x1, profileLine.y1);
    ctx.save();
    ctx.strokeStyle = '#7fd1ff';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(p0.x, p0.y);
    ctx.lineTo(p1.x, p1.y);
    ctx.stroke();
    ctx.fillStyle = '#7fd1ff';
    [p0, p1].forEach(p => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.restore();
  }

  /* ------------------------------------------------------------------ *
   * Measurement
   * ------------------------------------------------------------------ */

  function metresPerPixel() {
    const s = groundScale[scenes[a] && scenes[a].id];
    if (!s || !s.available || !grid) return null;
    return {
      x: s.ground_width_m / grid.w,
      y: s.ground_height_m / grid.h
    };
  }

  function formatDistance(metres) {
    if (metres === null) return null;
    return metres >= 1000 ? (metres / 1000).toFixed(3) + ' km' : metres.toFixed(1) + ' m';
  }

  function formatArea(squareMetres) {
    if (squareMetres === null) return null;
    if (squareMetres >= 1e6) return (squareMetres / 1e6).toFixed(4) + ' km²';
    if (squareMetres >= 1e4) return (squareMetres / 1e4).toFixed(3) + ' ha';
    return squareMetres.toFixed(1) + ' m²';
  }

  function measurementReadout() {
    if (!measurePoints.length) {
      return 'Click along a feature to measure. Two points give a distance; three or more also give an enclosed area.';
    }
    const mpp = metresPerPixel();
    let pixelLength = 0,
      groundLength = 0;
    for (let i = 1; i < measurePoints.length; i++) {
      const dx = measurePoints[i].x - measurePoints[i - 1].x;
      const dy = measurePoints[i].y - measurePoints[i - 1].y;
      pixelLength += Math.hypot(dx, dy);
      if (mpp) groundLength += Math.hypot(dx * mpp.x, dy * mpp.y);
    }
    const parts = [`${measurePoints.length} point(s)`];
    parts.push(mpp ? 'length ' + formatDistance(groundLength) : 'length ' + pixelLength.toFixed(1) + ' px');

    if (measurePoints.length > 2) {
      let twice = 0;
      for (let i = 0; i < measurePoints.length; i++) {
        const p = measurePoints[i],
          q = measurePoints[(i + 1) % measurePoints.length];
        twice += p.x * q.y - q.x * p.y;
      }
      const pixelArea = Math.abs(twice) / 2;
      parts.push(mpp ? 'area ' + formatArea(pixelArea * mpp.x * mpp.y) : 'area ' + pixelArea.toFixed(0) + ' px²');
    }
    parts.push(mpp ?
      'ground scale from the declared footprint (approximate, spherical)' :
      'no declared footprint for A, so only pixel units are available');
    return parts.join(' · ');
  }

  /* ------------------------------------------------------------------ *
   * Analysis panel
   * ------------------------------------------------------------------ */

  function panelActive() {
    return PANEL_TOOLS.includes(tool);
  }

  function drawPanel() {
    if (!panel) return;
    panel.hidden = !panelActive();
    if (!panelActive()) return;
    const w = panel.clientWidth,
      h = panel.clientHeight;
    if (!w || !h) return;
    panel.width = w * devicePixelRatio;
    panel.height = h * devicePixelRatio;
    panelCtx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    panelCtx.fillStyle = '#0a120f';
    panelCtx.fillRect(0, 0, w, h);
    if (tool === 'histogram') drawHistogramPanel(w, h);
    else if (tool === 'scatter') drawScatterPanel(w, h);
    else if (tool === 'profile') drawProfilePanel(w, h);
  }

  function axisFrame(w, h, pad) {
    panelCtx.strokeStyle = '#2f4a3a';
    panelCtx.lineWidth = 1;
    panelCtx.strokeRect(pad, pad, w - pad * 2, h - pad * 2);
  }

  function drawHistogramPanel(w, h) {
    if (!planes[a] || !planes[b]) return;
    const pad = 26;
    const hists = [a, b].map(i => {
      const data = rendered[i].getContext('2d').getImageData(0, 0, grid.w, grid.h);
      return window.ImageAnalysis.histogram(data).lum;
    });
    const peak = Math.max(1, ...hists.map(bins => Math.max(...bins)));
    axisFrame(w, h, pad);
    const colours = ['#c6ed70', '#7fd1ff'];
    hists.forEach((bins, k) => {
      panelCtx.strokeStyle = colours[k];
      panelCtx.lineWidth = 1.5;
      panelCtx.beginPath();
      for (let v = 0; v < 256; v++) {
        const x = pad + (w - pad * 2) * v / 255;
        const y = h - pad - (h - pad * 2) * bins[v] / peak;
        v ? panelCtx.lineTo(x, y) : panelCtx.moveTo(x, y);
      }
      panelCtx.stroke();
    });
    panelCtx.fillStyle = '#9fb8a5';
    panelCtx.font = '11px system-ui, sans-serif';
    panelCtx.fillText('Luminance histogram · dark → bright', pad, pad - 10);
    panelCtx.fillStyle = colours[0];
    panelCtx.fillText('A: ' + shortLabel(a), pad, h - 8);
    panelCtx.fillStyle = colours[1];
    panelCtx.fillText('B: ' + shortLabel(b), pad + 180, h - 8);
    panelCtx.fillStyle = '#9fb8a5';
    panelCtx.fillText('Two curves offset sideways indicate an illumination or exposure difference rather than ground change.', pad + 360, h - 8);
  }

  function drawScatterPanel(w, h) {
    if (!planes[a] || !planes[b]) return;
    const pad = 26;
    const joint = window.ImageAnalysis.jointHistogram(planes[a], planes[b], SCATTER_BINS);
    const size = Math.min(w - pad * 2, h - pad * 2);
    const left = pad,
      top = pad;
    axisFrame(w, h, pad);
    for (let y = 0; y < joint.size; y++) {
      for (let x = 0; x < joint.size; x++) {
        const count = joint.grid[y * joint.size + x];
        if (!count) continue;
        const t = Math.log(1 + count) / Math.log(1 + joint.peak);
        const rgb = window.ImageAnalysis.rampColour(t);
        panelCtx.fillStyle = `rgb(${rgb[0]|0},${rgb[1]|0},${rgb[2]|0})`;
        const cell = size / joint.size;
        panelCtx.fillRect(left + x * cell, top + size - (y + 1) * cell, Math.ceil(cell), Math.ceil(cell));
      }
    }
    panelCtx.strokeStyle = 'rgba(255,255,255,0.55)';
    panelCtx.setLineDash([4, 4]);
    panelCtx.beginPath();
    panelCtx.moveTo(left, top + size);
    panelCtx.lineTo(left + size, top);
    panelCtx.stroke();
    panelCtx.setLineDash([]);
    panelCtx.fillStyle = '#9fb8a5';
    panelCtx.font = '11px system-ui, sans-serif';
    panelCtx.fillText('A brightness →', left, h - 8);
    panelCtx.save();
    panelCtx.translate(12, top + size);
    panelCtx.rotate(-Math.PI / 2);
    panelCtx.fillText('B brightness →', 0, 0);
    panelCtx.restore();
    panelCtx.fillText('Pixels on the dashed diagonal held the same brightness on both dates; the further off it, the larger the change.',
      left + size + 16, top + 16);
    panelCtx.fillText(`${joint.counted.toLocaleString()} valid pixels compared.`, left + size + 16, top + 34);
  }

  function drawProfilePanel(w, h) {
    const pad = 26;
    axisFrame(w, h, pad);
    panelCtx.fillStyle = '#9fb8a5';
    panelCtx.font = '11px system-ui, sans-serif';
    if (!profileLine || !planes[a] || !planes[b]) {
      panelCtx.fillText('Drag a line across the imagery to plot brightness along it for both dates.', pad, h / 2);
      return;
    }
    const series = [a, b].map(i => window.ImageAnalysis.profile(
      planes[i], profileLine.x0, profileLine.y0, profileLine.x1, profileLine.y1, PROFILE_SAMPLES));
    const colours = ['#c6ed70', '#7fd1ff'];
    series.forEach((values, k) => {
      panelCtx.strokeStyle = colours[k];
      panelCtx.lineWidth = 1.5;
      panelCtx.beginPath();
      let started = false;
      values.forEach((v, s) => {
        if (v === null) {
          started = false;
          return;
        }
        const x = pad + (w - pad * 2) * s / (values.length - 1);
        const y = h - pad - (h - pad * 2) * v;
        started ? panelCtx.lineTo(x, y) : panelCtx.moveTo(x, y);
        started = true;
      });
      panelCtx.stroke();
    });
    const mpp = metresPerPixel();
    const dx = profileLine.x1 - profileLine.x0,
      dy = profileLine.y1 - profileLine.y0;
    const length = mpp ? formatDistance(Math.hypot(dx * mpp.x, dy * mpp.y)) :
      Math.hypot(dx, dy).toFixed(1) + ' px';
    panelCtx.fillStyle = '#9fb8a5';
    panelCtx.fillText('Brightness along the transect · length ' + length, pad, pad - 10);
    panelCtx.fillStyle = colours[0];
    panelCtx.fillText('A: ' + shortLabel(a), pad, h - 8);
    panelCtx.fillStyle = colours[1];
    panelCtx.fillText('B: ' + shortLabel(b), pad + 180, h - 8);
  }

  /* ------------------------------------------------------------------ *
   * Status line
   * ------------------------------------------------------------------ */

  function updateStatus() {
    let text;
    if (mode === 'blink' || mode === 'timeline') {
      text = `${timer?'Playing':'Paused'} · ${label(frame)}`;
    } else if (mode === 'composite') {
      const order = scenes.length > 2 ? [a, b, c] : [a, b, b];
      text = `Red ${shortLabel(order[0])} · Green ${shortLabel(order[1])} · Blue ${shortLabel(order[2])} — grey means the dates agree; a colour cast names the date that stands out.`;
    } else if (mode === 'difference') {
      const threshold = Number($('ivThreshold').value) / 100;
      const share = diff ? window.ImageAnalysis.changedFraction(diff, threshold) : 0;
      text = `A: ${label(a)} · B: ${label(b)} · ${(share*100).toFixed(2)}% of valid pixels differ by ${threshold.toFixed(2)} or more in luminance.`;
      if (heatCeiling !== null) {
        text += ` Ramp runs dark blue at ${threshold.toFixed(2)} to yellow at ${heatCeiling.toFixed(2)} (98th percentile of the flagged pixels).`;
      }
    } else {
      text = `A: ${label(a)} · B: ${label(b)}`;
    }
    if (tool === 'measure') text += ' — ' + measurementReadout();
    $('ivStatus').textContent = text;
  }

  /* ------------------------------------------------------------------ *
   * Modes, tools and lifecycle
   * ------------------------------------------------------------------ */

  function play() {
    if (timer) {
      stop();
      draw();
      return;
    }
    if (!['blink', 'timeline'].includes(mode)) setMode('blink');
    timer = setInterval(() => {
      frame = mode === 'blink' ? (frame === a ? b : a) : (frame + 1) % images.length;
      draw();
    }, Number($('ivSpeed').value));
    $('ivPlay').textContent = 'PAUSE';
    draw();
  }

  function syncControls() {
    $('ivBlendLabel').hidden = mode !== 'overlay';
    $('ivSpyLabel').hidden = mode !== 'spy';
    $('ivThresholdLabel').hidden = mode !== 'difference';
    $('ivHeatLabel').hidden = mode !== 'difference';
    $('ivCLabel').hidden = !(mode === 'composite' && scenes.length > 2);
    document.querySelectorAll('[data-inspect-mode]').forEach(x =>
      x.setAttribute('aria-pressed', String(x.dataset.inspectMode === mode)));
    document.querySelectorAll('[data-inspect-tool]').forEach(x =>
      x.setAttribute('aria-pressed', String(x.dataset.inspectTool === tool)));
  }

  function setMode(value) {
    stop();
    mode = value;
    frame = a;
    if (mode === 'side' && tool !== 'none') tool = 'none';
    syncControls();
    rebuild();
    if (mode === 'blink' || mode === 'timeline') play();
    else draw();
  }

  function setTool(value) {
    tool = tool === value ? 'none' : value;
    if (tool !== 'none' && mode === 'side') setMode('overlay');
    if (tool !== 'measure') measurePoints = [];
    if (tool !== 'profile') profileLine = null;
    /* Picking tools take over the drag gesture, so the cursor has to say so. */
    canvas.classList.toggle('ivPicking', tool === 'measure' || tool === 'profile');
    syncControls();
    draw();
  }

  async function loadGroundScale(index) {
    const scene = scenes[index];
    if (!scene || groundScale[scene.id] !== undefined) return;
    groundScale[scene.id] = {
      available: false
    };
    try {
      groundScale[scene.id] = await fetch('/api/scenes/' + scene.id + '/ground-scale').then(r => r.json());
    } catch (e) {
      /* Offline measurement simply falls back to pixels. */
    }
    draw();
  }

  function close() {
    stop();
    observer?.disconnect();
    modal?.remove();
    modal = null;
    canvas = null;
    panel = null;
    images = [];
    rendered = {};
    planes = {};
    composite = diff = heat = grid = view = null;
    measurePoints = [];
    profileLine = null;
    document.removeEventListener('keydown', keys);
  }

  function keys(e) {
    if (e.key === 'Escape') close();
  }

  function controlsMarkup() {
    const modeButtons = MODES.map(m =>
      `<button data-inspect-mode="${m}" aria-pressed="${m==='side'}">${MODE_LABELS[m]}</button>`).join('');
    const toolButtons = PANEL_TOOLS.concat(['measure']).map(t =>
      `<button data-inspect-tool="${t}" aria-pressed="false">${t.toUpperCase()}</button>`).join('');
    return `<div class="ivHeader"><b>IMAGE COMPARISON / LOCAL EVIDENCE</b><button id="ivClose">CLOSE</button></div>` +
      `<div class="ivControls">${modeButtons}<button id="ivPlay">PLAY</button>` +
      `<label>Interval <select id="ivSpeed"><option value="500">0.5 sec</option><option value="1000" selected>1 sec</option><option value="2000">2 sec</option></select></label>` +
      `<button id="ivMinus">−</button><span id="ivZoomText">1×</span><button id="ivPlus">+</button>` +
      `<button id="ivReset">RESET VIEW</button><button id="ivFull">FULL SCREEN</button></div>` +
      `<div class="ivControls"><label>A <select id="ivA"></select></label><label>B <select id="ivB"></select></label>` +
      `<label id="ivCLabel" hidden>C <select id="ivC"></select></label>` +
      `<label id="ivBlendLabel" hidden>Blend <input id="ivBlend" type="range" min="0" max="100" value="50"></label>` +
      `<label id="ivSpyLabel" hidden>Lens radius <input id="ivSpyRadius" type="range" min="40" max="320" value="120"></label>` +
      `<label id="ivThresholdLabel" hidden>Change threshold <input id="ivThreshold" type="range" min="2" max="60" value="18"></label>` +
      `<label id="ivHeatLabel" hidden>Overlay <input id="ivHeatOpacity" type="range" min="10" max="100" value="80"></label></div>` +
      `<div class="ivControls"><label>Stretch <select id="ivStretch">` +
      `<option value="none" selected>None</option><option value="linear2">Linear 2% clip</option>` +
      `<option value="linear5">Linear 5% clip</option><option value="stddev">Mean ± 2σ</option>` +
      `<option value="equalize">Histogram equalise</option><option value="gamma">Gamma</option></select></label>` +
      `<label>Gamma <input id="ivGamma" type="range" min="30" max="300" value="100"></label>` +
      `<span class="ivToolGroup">${toolButtons}</span></div>` +
      `<p id="ivStretchNote" class="hint"></p>` +
      `<p id="ivStatus" role="status">Loading original previews…</p>` +
      `<canvas id="ivCanvas" aria-label="Comparison images; drag to pan and scroll to zoom"></canvas>` +
      `<canvas id="ivPanel" aria-label="Analysis plot" hidden></canvas>` +
      `<small>Drag to pan · wheel or +/− to zoom · shared view across both images · visual inspection only; overlays do not automatically georegister sources. Pixel tools work on a shared reference grid, so a differently sized date is resampled onto A's grid before anything is compared.</small>`;
  }

  window.openImageInspector = async function(inputScenes) {
    close();
    scenes = (inputScenes || []).filter(Boolean);
    if (scenes.length < 2) return;
    a = 0;
    b = 1;
    c = Math.min(2, scenes.length - 1);
    frame = 0;
    zoom = 1;
    pan = {
      x: 0,
      y: 0
    };
    mode = 'side';
    tool = 'none';
    measurePoints = [];
    profileLine = null;
    groundScale = {};

    modal = document.createElement('div');
    modal.id = 'imageInspector';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Image comparison inspector');
    modal.innerHTML = controlsMarkup();
    document.body.append(modal);
    canvas = $('ivCanvas');
    ctx = canvas.getContext('2d');
    panel = $('ivPanel');
    panelCtx = panel.getContext('2d');

    for (const name of ['ivA', 'ivB', 'ivC']) {
      scenes.forEach((s, i) => $(name).add(new Option(label(i), String(i))));
    }
    $('ivB').value = '1';
    $('ivC').value = String(c);

    $('ivClose').onclick = close;
    document.addEventListener('keydown', keys);
    $('ivClose').focus();
    document.querySelectorAll('[data-inspect-mode]').forEach(x =>
      x.onclick = () => setMode(x.dataset.inspectMode));
    document.querySelectorAll('[data-inspect-tool]').forEach(x =>
      x.onclick = () => setTool(x.dataset.inspectTool));
    $('ivPlay').onclick = play;
    $('ivSpeed').onchange = () => {
      if (timer) {
        stop();
        play();
      }
    };

    const pair = () => {
      stop();
      a = Number($('ivA').value);
      b = Number($('ivB').value);
      c = Number($('ivC').value);
      frame = a;
      measurePoints = [];
      profileLine = null;
      rebuild();
      loadGroundScale(a);
      draw();
    };
    $('ivA').onchange = pair;
    $('ivB').onchange = pair;
    $('ivC').onchange = pair;
    $('ivBlend').oninput = draw;
    $('ivSpyRadius').oninput = draw;
    $('ivHeatOpacity').oninput = draw;
    $('ivThreshold').oninput = () => {
      heat = null;
      heatCeiling = null;
      draw();
    };
    $('ivStretch').onchange = () => {
      rebuild();
      draw();
    };
    $('ivGamma').oninput = () => {
      if ($('ivStretch').value !== 'gamma') return;
      rebuild();
      draw();
    };

    function scale(delta) {
      zoom = Math.max(.5, Math.min(8, zoom * delta));
      draw();
    }
    $('ivPlus').onclick = () => scale(1.25);
    $('ivMinus').onclick = () => scale(.8);
    $('ivReset').onclick = () => {
      zoom = 1;
      pan = {
        x: 0,
        y: 0
      };
      draw();
    };
    $('ivFull').onclick = async () => {
      try {
        if (document.fullscreenElement) await document.exitFullscreen();
        else await modal.requestFullscreen();
      } catch (e) {
        $('ivStatus').textContent = 'Browser fullscreen unavailable; the viewer already fills the window.';
      }
    };

    canvas.onwheel = e => {
      e.preventDefault();
      scale(e.deltaY < 0 ? 1.12 : 1 / 1.12);
    };
    canvas.onpointerdown = e => {
      const at = pointerPosition(e);
      if (tool === 'measure' && view) {
        const p = canvasToImage(at.x, at.y);
        if (p.x >= 0 && p.y >= 0 && grid && p.x <= grid.w && p.y <= grid.h) {
          measurePoints.push(p);
          draw();
          return;
        }
      }
      if (tool === 'profile' && view) {
        const p = canvasToImage(at.x, at.y);
        profileDrag = p;
        profileLine = {
          x0: p.x,
          y0: p.y,
          x1: p.x,
          y1: p.y
        };
        canvas.setPointerCapture(e.pointerId);
        draw();
        return;
      }
      drag = {
        x: e.clientX,
        y: e.clientY
      };
      canvas.setPointerCapture(e.pointerId);
    };
    canvas.onpointermove = e => {
      pointer = pointerPosition(e);
      if (profileDrag && view) {
        const p = canvasToImage(pointer.x, pointer.y);
        profileLine = {
          x0: profileDrag.x,
          y0: profileDrag.y,
          x1: p.x,
          y1: p.y
        };
        draw();
        return;
      }
      if (drag) {
        pan.x += e.clientX - drag.x;
        pan.y += e.clientY - drag.y;
        drag = {
          x: e.clientX,
          y: e.clientY
        };
        draw();
        return;
      }
      if (mode === 'spy') draw();
    };
    canvas.onpointerup = canvas.onpointercancel = () => {
      drag = null;
      profileDrag = null;
    };
    canvas.ondblclick = () => {
      if (tool === 'measure') {
        measurePoints = [];
        draw();
      }
    };

    observer = new ResizeObserver(draw);
    observer.observe(canvas);

    const current = modal;
    try {
      const loaded = await Promise.all(scenes.map(s => new Promise((resolve, reject) => {
        const im = new Image();
        im.onload = () => resolve(im);
        im.onerror = () => reject(Error('An image preview could not be loaded. Close and check the source in Data Library.'));
        im.src = '/api/scenes/' + s.id + '/preview';
      })));
      if (modal !== current) return;
      images = loaded;
      rebuild();
      syncControls();
      loadGroundScale(a);
      draw();
    } catch (e) {
      if (modal === current) $('ivStatus').textContent = e.message;
    }
  };

  window.compareClusterSelected = async function() {
    const ids = [...document.querySelectorAll('#clusterModalGrid input:checked')].map(x => Number(x.value));
    if (ids.length < 2) return;
    const selected = ids.map(id => (window.activeClusterScenes || []).find(s => s.id === id)).filter(Boolean);
    window.openImageInspector(selected);
  };
})();
