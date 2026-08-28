/* Shared palette and formatting.
 *
 * The risk ramp is the thermal ramp. A hotter colour means a worse number, whether it
 * is painted on a camera overlay, a map cell or the risk ledger, so the operator only
 * has to learn the scale once.
 */
window.RESQ = (function () {
  var STOPS = [
    { at: 0,   rgb: [63, 191, 106] },   // safe
    { at: 30,  rgb: [242, 195, 0] },    // hi-vis caution
    { at: 62,  rgb: [255, 122, 31] },   // ember
    { at: 100, rgb: [255, 59, 48] }     // flare
  ];

  function ramp(value, alpha) {
    var v = Math.max(0, Math.min(100, value || 0));
    var lo = STOPS[0], hi = STOPS[STOPS.length - 1];
    for (var i = 0; i < STOPS.length - 1; i++) {
      if (v >= STOPS[i].at && v <= STOPS[i + 1].at) { lo = STOPS[i]; hi = STOPS[i + 1]; break; }
    }
    var t = hi.at === lo.at ? 0 : (v - lo.at) / (hi.at - lo.at);
    var c = [0, 1, 2].map(function (k) { return Math.round(lo.rgb[k] + (hi.rgb[k] - lo.rgb[k]) * t); });
    return alpha === undefined
      ? 'rgb(' + c.join(',') + ')'
      : 'rgba(' + c.join(',') + ',' + alpha + ')';
  }

  /* Risk bands and confidence bands get their own scales.
   *
   * The ramp is right for a hazard field, where low really is safe. It is wrong for the
   * headline score and for detection confidence: a green "15" reads as all-clear when
   * what it means is "one survivor, no hazards measured yet", and a green 40% confidence
   * reads as good news when it means the opposite. Both scales start neutral instead. */
  var BAND_COLOR = {
    LOW: '#97A2A5', MEDIUM: '#F2C300', HIGH: '#FF7A1F', CRITICAL: '#FF3B30'
  };
  function bandColor(band) { return BAND_COLOR[band] || '#97A2A5'; }

  function confidenceColor(c) {
    if (c >= 0.85) return '#FF3B30';        // confirmed — act on it
    if (c >= 0.60) return '#FF7A1F';        // probable
    if (c >= 0.35) return '#F2C300';        // possible
    return '#97A2A5';                       // weak, but never "fine"
  }

  var CLASS_COLOR = {
    person: '#FF3B30',
    fire: '#FF7A1F',
    smoke: '#97A2A5',
    debris: '#F2C300',
    obstacle: '#F2C300'
  };

  function classColor(cls) { return CLASS_COLOR[cls] || '#E7EAE8'; }

  function pct(v) { return v === null || v === undefined ? '--' : Math.round(v * 100) + '%'; }

  function clock(seconds) {
    var s = Math.max(0, Math.floor(seconds || 0));
    var m = Math.floor(s / 60);
    return String(m).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
  }

  /* Fit a canvas to its box at device resolution.
   *
   * The size is observed, not measured: reading getBoundingClientRect inside the draw
   * loop forces a layout on every animation frame, twice over, for a number that only
   * changes when the window does.
   */
  var sizes = new WeakMap();

  function observe(canvas) {
    var entry = { w: 0, h: 0, dirty: true };
    sizes.set(canvas, entry);
    var apply = function (w, h) {
      entry.w = Math.max(1, Math.round(w));
      entry.h = Math.max(1, Math.round(h));
      entry.dirty = true;
    };
    if (window.ResizeObserver) {
      new ResizeObserver(function (records) {
        var r = records[records.length - 1];
        var box = r.contentRect;
        apply(box.width, box.height);
      }).observe(canvas);
    } else {
      window.addEventListener('resize', function () {
        var box = canvas.getBoundingClientRect();
        apply(box.width, box.height);
      });
    }
    var box = canvas.getBoundingClientRect();
    apply(box.width, box.height);
    return entry;
  }

  function fit(canvas) {
    var entry = sizes.get(canvas) || observe(canvas);
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    var ctx = canvas.getContext('2d');
    if (entry.dirty || canvas.width !== entry.w * dpr) {
      canvas.width = entry.w * dpr;
      canvas.height = entry.h * dpr;
      entry.dirty = false;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, w: entry.w, h: entry.h };
  }

  /* Canvas motion is outside CSS, so it has to check the preference itself. */
  var motionQuery = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  function stillTime(t) { return motionQuery && motionQuery.matches ? 0 : t; }

  /* Deterministic noise so the simulated scene does not shimmer between frames. */
  function hash(n) {
    var x = Math.sin(n * 127.1) * 43758.5453;
    return x - Math.floor(x);
  }

  return { ramp: ramp, bandColor: bandColor, confidenceColor: confidenceColor,
           classColor: classColor, pct: pct, clock: clock, fit: fit,
           hash: hash, stillTime: stillTime };
})();
