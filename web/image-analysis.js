/* Pixel analysis for the comparison viewer. Pure functions, no DOM, no network.
 *
 * These are the standard visual-interpretation operations an imagery analyst
 * reaches for -- contrast stretch, histogram, band/date compositing, difference
 * and profiling. They are deliberately kept apart from the viewer so each one
 * can be reasoned about and corrected on its own.
 *
 * Everything here is display arithmetic on 8-bit RGB previews. None of it is a
 * radiometric or spectral product: the previews have already been stretched for
 * display, and the archive's fourth band is an alpha channel rather than
 * near-infrared, so no vegetation or water index is computed anywhere. Treat
 * every output as a visual aid, never as a measurement of reflectance.
 */
(() => {
  'use strict';

  const clamp8 = v => v < 0 ? 0 : v > 255 ? 255 : v | 0;

  /* Rec. 709 luminance, the same weighting the server-side screening uses. */
  const LUM_R = 0.2126,
    LUM_G = 0.7152,
    LUM_B = 0.0722;

  /** Draw an image onto an offscreen canvas at a fixed size and read it back. */
  function toImageData(img, width, height) {
    const c = document.createElement('canvas');
    c.width = Math.max(1, width | 0);
    c.height = Math.max(1, height | 0);
    const g = c.getContext('2d', {
      willReadFrequently: true
    });
    g.drawImage(img, 0, 0, c.width, c.height);
    return g.getImageData(0, 0, c.width, c.height);
  }

  /** Per-channel and luminance histograms, 256 bins, ignoring transparent pixels. */
  function histogram(data) {
    const d = data.data,
      r = new Uint32Array(256),
      g = new Uint32Array(256),
      b = new Uint32Array(256),
      lum = new Uint32Array(256);
    let counted = 0;
    for (let i = 0; i < d.length; i += 4) {
      if (d[i + 3] < 8) continue;
      r[d[i]]++;
      g[d[i + 1]]++;
      b[d[i + 2]]++;
      lum[clamp8(LUM_R * d[i] + LUM_G * d[i + 1] + LUM_B * d[i + 2])]++;
      counted++;
    }
    return {
      r: r,
      g: g,
      b: b,
      lum: lum,
      counted: counted
    };
  }

  /** The value below which `fraction` of the population falls. */
  function percentileFromHistogram(bins, counted, fraction) {
    const target = counted * fraction;
    let running = 0;
    for (let v = 0; v < 256; v++) {
      running += bins[v];
      if (running >= target) return v;
    }
    return 255;
  }

  function meanStd(bins, counted) {
    let sum = 0;
    for (let v = 0; v < 256; v++) sum += v * bins[v];
    const mean = counted ? sum / counted : 0;
    let variance = 0;
    for (let v = 0; v < 256; v++) variance += bins[v] * (v - mean) * (v - mean);
    return {
      mean: mean,
      std: counted ? Math.sqrt(variance / counted) : 0
    };
  }

  function rampLUT(low, high) {
    const lut = new Uint8Array(256);
    const span = Math.max(1, high - low);
    for (let v = 0; v < 256; v++) lut[v] = clamp8((v - low) * 255 / span);
    return lut;
  }

  function equalizeLUT(bins, counted) {
    const lut = new Uint8Array(256);
    if (!counted) return rampLUT(0, 255);
    let running = 0;
    for (let v = 0; v < 256; v++) {
      running += bins[v];
      lut[v] = clamp8(running * 255 / counted);
    }
    return lut;
  }

  function gammaLUT(gamma) {
    const lut = new Uint8Array(256);
    const inverse = 1 / Math.max(0.05, gamma);
    for (let v = 0; v < 256; v++) lut[v] = clamp8(255 * Math.pow(v / 255, inverse));
    return lut;
  }

  /**
   * Build one lookup table per channel for a named stretch.
   *
   * Each channel is stretched on its own statistics, which is what image
   * processing packages do by default. It aids the eye; it does not preserve
   * radiometric comparability between two dates, and the caller is expected to
   * say so in the interface.
   */
  function stretchLUTs(data, method, gamma) {
    const h = histogram(data);
    const channels = [h.r, h.g, h.b];
    if (method === 'none') {
      const identity = rampLUT(0, 255);
      return {
        luts: [identity, identity, identity],
        description: 'no stretch; preview values shown as stored'
      };
    }
    if (method === 'gamma') {
      const lut = gammaLUT(gamma);
      return {
        luts: [lut, lut, lut],
        description: 'gamma ' + Number(gamma).toFixed(2)
      };
    }
    if (method === 'equalize') {
      return {
        luts: channels.map(bins => equalizeLUT(bins, h.counted)),
        description: 'histogram equalisation, per channel'
      };
    }
    if (method === 'stddev') {
      return {
        luts: channels.map(bins => {
          const s = meanStd(bins, h.counted);
          return rampLUT(Math.round(s.mean - 2 * s.std), Math.round(s.mean + 2 * s.std));
        }),
        description: 'mean ± 2 standard deviations, per channel'
      };
    }
    const cut = method === 'linear5' ? 0.05 : 0.02;
    return {
      luts: channels.map(bins => rampLUT(
        percentileFromHistogram(bins, h.counted, cut),
        percentileFromHistogram(bins, h.counted, 1 - cut)
      )),
      description: 'linear ' + Math.round(cut * 100) + '% clip, per channel'
    };
  }

  /** Apply per-channel LUTs, returning a new ImageData. */
  function applyLUTs(data, luts) {
    const out = new ImageData(data.width, data.height);
    const s = data.data,
      o = out.data;
    for (let i = 0; i < s.length; i += 4) {
      o[i] = luts[0][s[i]];
      o[i + 1] = luts[1][s[i + 1]];
      o[i + 2] = luts[2][s[i + 2]];
      o[i + 3] = s[i + 3];
    }
    return out;
  }

  /** Luminance plane, 0..1, with a parallel validity mask. */
  function luminance(data) {
    const d = data.data,
      n = data.width * data.height,
      out = new Float32Array(n),
      valid = new Uint8Array(n);
    for (let p = 0, i = 0; p < n; p++, i += 4) {
      out[p] = (LUM_R * d[i] + LUM_G * d[i + 1] + LUM_B * d[i + 2]) / 255;
      valid[p] = d[i + 3] >= 8 ? 1 : 0;
    }
    return {
      values: out,
      valid: valid,
      width: data.width,
      height: data.height
    };
  }

  /**
   * Multi-temporal colour composite: one date per output channel.
   *
   * Grey means all the supplied dates agree at that pixel. A colour cast means
   * one date is brighter than the others, and the hue says which -- red for the
   * first, green for the second, blue for the third. This is the classic
   * multi-date composite used for visual change screening. With two dates the
   * second is repeated into green and blue, so gains read cyan and losses red.
   */
  function temporalComposite(planes, width, height) {
    if (!planes.length) return null;
    const pick = planes.length >= 3 ? [planes[0], planes[1], planes[2]] :
      [planes[0], planes[1], planes[1]];
    const out = new ImageData(width, height);
    const o = out.data,
      n = width * height;
    for (let p = 0, i = 0; p < n; p++, i += 4) {
      const ok = pick[0].valid[p] && pick[1].valid[p] && pick[2].valid[p];
      o[i] = clamp8(pick[0].values[p] * 255);
      o[i + 1] = clamp8(pick[1].values[p] * 255);
      o[i + 2] = clamp8(pick[2].values[p] * 255);
      o[i + 3] = ok ? 255 : 0;
    }
    return out;
  }

  /** Absolute luminance difference, 0..1, invalid where either date is masked. */
  function difference(first, second) {
    const n = Math.min(first.values.length, second.values.length),
      out = new Float32Array(n),
      valid = new Uint8Array(n);
    for (let p = 0; p < n; p++) {
      valid[p] = first.valid[p] && second.valid[p] ? 1 : 0;
      out[p] = valid[p] ? Math.abs(first.values[p] - second.values[p]) : 0;
    }
    return {
      values: out,
      valid: valid,
      width: first.width,
      height: first.height
    };
  }

  /* Perceptually ordered ramp: dark blue (no change) to yellow (most change).
   * Chosen so the ordering survives greyscale printing and the common forms of
   * colour vision deficiency, unlike a red-green ramp. */
  const RAMP = [
    [12, 24, 60],
    [28, 82, 130],
    [30, 140, 130],
    [120, 180, 80],
    [240, 220, 70]
  ];

  function rampColour(t) {
    const x = Math.max(0, Math.min(1, t)) * (RAMP.length - 1);
    const i = Math.min(RAMP.length - 2, Math.floor(x)),
      f = x - i;
    const lo = RAMP[i],
      hi = RAMP[i + 1];
    return [
      lo[0] + (hi[0] - lo[0]) * f,
      lo[1] + (hi[1] - lo[1]) * f,
      lo[2] + (hi[2] - lo[2]) * f
    ];
  }

  /**
   * Colour-ramp a difference plane. Pixels below `threshold` stay transparent so
   * the imagery underneath remains readable and only flagged change is tinted.
   *
   * The ramp is scaled to the 98th percentile of the differences that actually
   * clear the threshold, not to the theoretical maximum of 1.0. Two dates never
   * differ by the full luminance range, so scaling to 1.0 pinned every pixel at
   * the cold end of the ramp and the colour carried no information. The ceiling
   * is returned so the interface can state what the top of the scale means.
   */
  function heatmap(diff, threshold) {
    const out = new ImageData(diff.width, diff.height);
    const o = out.data,
      n = diff.values.length;

    const above = [];
    for (let p = 0; p < n; p++) {
      if (diff.valid[p] && diff.values[p] >= threshold) above.push(diff.values[p]);
    }
    above.sort((x, y) => x - y); // numeric: the default sort is lexicographic
    const ceiling = above.length ?
      Math.max(threshold + 0.02, above[Math.min(above.length - 1, Math.floor(above.length * 0.98))]) :
      1;
    const span = Math.max(1e-6, ceiling - threshold);

    for (let p = 0, i = 0; p < n; p++, i += 4) {
      if (!diff.valid[p] || diff.values[p] < threshold) {
        o[i + 3] = 0;
        continue;
      }
      const t = Math.min(1, (diff.values[p] - threshold) / span);
      const c = rampColour(t);
      o[i] = clamp8(c[0]);
      o[i + 1] = clamp8(c[1]);
      o[i + 2] = clamp8(c[2]);
      o[i + 3] = clamp8(90 + 165 * t);
    }
    return {
      data: out,
      ceiling: ceiling,
      flagged: above.length
    };
  }

  /** Sample a luminance plane along a straight line, nearest neighbour. */
  function profile(plane, x0, y0, x1, y1, samples) {
    const out = [];
    const count = Math.max(2, samples | 0);
    for (let s = 0; s < count; s++) {
      const t = s / (count - 1);
      const x = Math.round(x0 + (x1 - x0) * t),
        y = Math.round(y0 + (y1 - y0) * t);
      if (x < 0 || y < 0 || x >= plane.width || y >= plane.height) {
        out.push(null);
        continue;
      }
      const p = y * plane.width + x;
      out.push(plane.valid[p] ? plane.values[p] : null);
    }
    return out;
  }

  /**
   * Joint histogram of two dates, for the before-versus-after scatter.
   *
   * Pixels on the diagonal held the same brightness on both dates. Pixels off
   * it changed, and which side of the diagonal says whether they brightened or
   * darkened. Counts are returned rather than points so the plot stays cheap
   * on a full-size image.
   */
  function jointHistogram(first, second, bins) {
    const size = Math.max(8, bins | 0);
    const grid = new Uint32Array(size * size);
    const n = Math.min(first.values.length, second.values.length);
    let counted = 0,
      peak = 0;
    for (let p = 0; p < n; p++) {
      if (!first.valid[p] || !second.valid[p]) continue;
      const x = Math.min(size - 1, (first.values[p] * size) | 0);
      const y = Math.min(size - 1, (second.values[p] * size) | 0);
      const at = y * size + x;
      grid[at]++;
      counted++;
      if (grid[at] > peak) peak = grid[at];
    }
    return {
      grid: grid,
      size: size,
      counted: counted,
      peak: peak
    };
  }

  /** Share of valid pixels whose difference clears a threshold. */
  function changedFraction(diff, threshold) {
    let valid = 0,
      over = 0;
    for (let p = 0; p < diff.values.length; p++) {
      if (!diff.valid[p]) continue;
      valid++;
      if (diff.values[p] >= threshold) over++;
    }
    return valid ? over / valid : 0;
  }

  window.ImageAnalysis = {
    toImageData: toImageData,
    histogram: histogram,
    stretchLUTs: stretchLUTs,
    applyLUTs: applyLUTs,
    luminance: luminance,
    temporalComposite: temporalComposite,
    difference: difference,
    heatmap: heatmap,
    rampColour: rampColour,
    profile: profile,
    jointHistogram: jointHistogram,
    changedFraction: changedFraction
  };
})();
