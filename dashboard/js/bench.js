/* The detector bench — the perception layer, on the viewer's own camera.
 *
 * Anyone who opens this board can point their camera at something and watch the same
 * two models the rover carries do their work. It answers the one question a live board
 * cannot: is the detection real, or is this a mock-up?
 *
 * It is deliberately NOT a rover.
 *
 * The server holds one mission. If every visitor's browser pushed frames to /ws/rover,
 * two visitors would be two cameras overwriting each other on one shared board, and
 * everyone would watch a stranger's room flicker against the incident. Worse, the rover
 * token would have to ship in this file, where anyone could read it and invent survivors
 * on a live rescue board.
 *
 * So nothing here leaves the machine it runs on. The camera is read locally, inference
 * runs locally in WebAssembly, the boxes are drawn locally, and the mission on the board
 * behind this panel is untouched. Each viewer benches their own camera. The server pays
 * nothing -- which matters, because it is one shared vCPU.
 *
 * The weights are the same ones the rover carries, exported to ONNX. What you see here
 * is what the rover would see.
 */
window.Bench = (function () {
  var INPUT = 416;              // matches the rover's --imgsz, so scores are comparable
  var PAD = 114;                // YOLO's letterbox grey
  var IOU = 0.45;

  /* Same models, same floors and same class mapping as rover/perception.py. A class the
     risk engine cannot score is dropped here too -- COCO's other 79 are not evidence. */
  var MODELS = [
    { file: 'models/fire_smoke.onnx', floor: 0.30, map: { 0: 'fire', 1: 'smoke' } },
    { file: 'models/yolov8n.onnx', floor: 0.35, map: { 0: 'person' } }
  ];

  var sessions = null;
  var stream = null;
  var running = false;
  var loading = false;
  var video, canvas, ctx, work, wctx;
  var panel, statusEl, listEl, startBtn;
  var lastMs = 0;

  function $(id) { return document.getElementById(id); }

  function say(text, kind) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.dataset.kind = kind || '';
  }

  /* ── loading ──────────────────────────────────────────────────────────────
   * 24 MB of weights and 11 MB of runtime. Nobody who just wants to watch the
   * board should pay that, so none of it is fetched until the bench is opened. */

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = function () { reject(new Error('could not load ' + src)); };
      document.head.appendChild(s);
    });
  }

  function loadSessions() {
    if (sessions) return Promise.resolve(sessions);
    if (loading) return Promise.reject(new Error('already loading'));
    loading = true;

    say('Loading the detector — 35 MB, once.', 'busy');
    return loadScript('vendor/ort/ort.wasm.min.js').then(function () {
      // Absolute, not relative: the runtime dynamically imports its loader module from
      // here, and a bare relative path is read as a module specifier rather than a URL.
      ort.env.wasm.wasmPaths = new URL('vendor/ort/', document.baseURI).href;
      // One thread on purpose: more would need cross-origin isolation headers this
      // host does not send, and the page would fail rather than run slower.
      ort.env.wasm.numThreads = 1;
      ort.env.wasm.simd = true;
      ort.env.logLevel = 'error';

      return Promise.all(MODELS.map(function (m) {
        return ort.InferenceSession.create(m.file, { executionProviders: ['wasm'] })
          .then(function (session) { return { session: session, spec: m }; });
      }));
    }).then(function (loaded) {
      sessions = loaded;
      loading = false;
      return sessions;
    }).catch(function (err) {
      loading = false;
      throw err;
    });
  }

  /* ── the frame, in the shape the model wants ──────────────────────────────
   * Letterbox: scale to fit, pad the rest grey, keep the aspect ratio. Stretching
   * instead would squash a standing person into the model's idea of nothing. */

  function letterbox() {
    var vw = video.videoWidth, vh = video.videoHeight;
    var scale = Math.min(INPUT / vw, INPUT / vh);
    var dw = Math.round(vw * scale), dh = Math.round(vh * scale);
    var dx = Math.floor((INPUT - dw) / 2), dy = Math.floor((INPUT - dh) / 2);

    wctx.fillStyle = 'rgb(' + PAD + ',' + PAD + ',' + PAD + ')';
    wctx.fillRect(0, 0, INPUT, INPUT);
    wctx.drawImage(video, dx, dy, dw, dh);

    var px = wctx.getImageData(0, 0, INPUT, INPUT).data;
    var n = INPUT * INPUT;
    var data = new Float32Array(3 * n);
    for (var i = 0; i < n; i++) {
      data[i] = px[i * 4] / 255;                 // R plane
      data[n + i] = px[i * 4 + 1] / 255;         // G plane
      data[2 * n + i] = px[i * 4 + 2] / 255;     // B plane
    }
    return { tensor: new ort.Tensor('float32', data, [1, 3, INPUT, INPUT]),
             scale: scale, dx: dx, dy: dy };
  }

  /* ── reading the model back ───────────────────────────────────────────────
   * YOLOv8 returns [1, 4 + classes, anchors], laid out plane by plane: every anchor's
   * cx sits together, then every cy, and so on. Boxes are centre-width-height in the
   * letterboxed frame, so they have to be un-padded and un-scaled before they mean
   * anything on the real picture. */

  function decode(output, box, spec) {
    var d = output.data;
    var dims = output.dims;                     // [1, 4 + nc, anchors]
    var chan = dims[1], anchors = dims[2];
    var nc = chan - 4;
    var out = [];

    for (var i = 0; i < anchors; i++) {
      var best = -1, bestScore = 0;
      for (var c = 0; c < nc; c++) {
        var s = d[(4 + c) * anchors + i];
        if (s > bestScore) { bestScore = s; best = c; }
      }
      if (bestScore < spec.floor) continue;
      var cls = spec.map[best];
      if (!cls) continue;                       // a class this rover does not forward

      var cx = d[i], cy = d[anchors + i];
      var w = d[2 * anchors + i], h = d[3 * anchors + i];
      out.push({
        cls: cls,
        conf: bestScore,
        x: (cx - w / 2 - box.dx) / box.scale,
        y: (cy - h / 2 - box.dy) / box.scale,
        w: w / box.scale,
        h: h / box.scale
      });
    }
    return out;
  }

  function iou(a, b) {
    var x = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
    var y = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
    var inter = x * y;
    var union = a.w * a.h + b.w * b.h - inter;
    return union > 0 ? inter / union : 0;
  }

  /* Greedy suppression, per class: one object should be one box, not the forty
     overlapping guesses the anchor grid produces for it. */
  function nms(boxes) {
    var kept = [];
    boxes.sort(function (p, q) { return q.conf - p.conf; });
    for (var i = 0; i < boxes.length; i++) {
      var drop = false;
      for (var j = 0; j < kept.length; j++) {
        if (kept[j].cls === boxes[i].cls && iou(kept[j], boxes[i]) > IOU) { drop = true; break; }
      }
      if (!drop) kept.push(boxes[i]);
    }
    return kept;
  }

  /* ── drawing ──────────────────────────────────────────────────────────── */

  function paint(dets) {
    var vw = video.videoWidth, vh = video.videoHeight;
    if (canvas.width !== vw || canvas.height !== vh) {
      canvas.width = vw; canvas.height = vh;
    }
    ctx.clearRect(0, 0, vw, vh);
    ctx.lineWidth = Math.max(2, vw / 320);
    // Keep the size in a variable. Reading it back out of ctx.font parses the weight,
    // not the size -- "600 15px ..." yields 600, and every label becomes a 610px slab.
    var size = Math.max(13, Math.round(vw / 42));
    var pad = 5;
    var th = size + pad * 2;
    ctx.font = '600 ' + size + 'px "IBM Plex Mono", monospace';
    ctx.textBaseline = 'top';

    dets.forEach(function (d) {
      var colour = window.RESQ ? RESQ.classColor(d.cls) : '#F2C300';
      ctx.strokeStyle = colour;
      ctx.strokeRect(d.x, d.y, d.w, d.h);

      var label = d.cls.toUpperCase() + ' ' + Math.round(d.conf * 100) + '%';
      var tw = ctx.measureText(label).width;
      // Above the box, unless it would fall off the top of the frame.
      var ly = d.y > th ? d.y - th : d.y;
      ctx.fillStyle = colour;
      ctx.fillRect(d.x, ly, tw + pad * 2, th);
      ctx.fillStyle = '#0E1113';
      ctx.fillText(label, d.x + pad, ly + pad);
    });
  }

  function list(dets, ms) {
    if (!listEl) return;
    if (!dets.length) {
      listEl.innerHTML = '<li class="bench__none">Nothing in view.</li>';
    } else {
      listEl.innerHTML = dets.map(function (d) {
        var colour = window.RESQ ? RESQ.classColor(d.cls) : '#F2C300';
        return '<li class="bench__row">'
             + '<span class="bench__cls" style="color:' + colour + '">' + d.cls + '</span>'
             + '<span class="bench__bar"><i style="width:' + Math.round(d.conf * 100)
             + '%;background:' + colour + '"></i></span>'
             + '<span class="bench__pct">' + Math.round(d.conf * 100) + '%</span></li>';
      }).join('');
    }
    say(Math.round(ms) + ' ms per frame · ' + (ms > 0 ? (1000 / ms).toFixed(1) : '0')
        + ' fps · your camera, this machine', 'live');
  }

  /* ── the loop ─────────────────────────────────────────────────────────── */

  function step() {
    if (!running) return;
    var t0 = performance.now();
    var box;
    try {
      box = letterbox();
    } catch (e) {
      // The camera can vanish mid-run: a lid closing, another application taking it.
      setTimeout(step, 300);
      return;
    }

    Promise.all(sessions.map(function (s) {
      var feeds = {};
      feeds[s.session.inputNames[0]] = box.tensor;
      return s.session.run(feeds).then(function (res) {
        return decode(res[s.session.outputNames[0]], box, s.spec);
      });
    })).then(function (perModel) {
      if (!running) return;
      var dets = nms(perModel.reduce(function (a, b) { return a.concat(b); }, []));
      paint(dets);
      lastMs = lastMs ? lastMs * 0.8 + (performance.now() - t0) * 0.2
                      : performance.now() - t0;
      list(dets, lastMs);
      setTimeout(step, 0);
    }).catch(function (err) {
      say('Detector stopped: ' + err.message, 'bad');
      running = false;
    });
  }

  /* ── lifecycle ────────────────────────────────────────────────────────── */

  function start() {
    if (running || loading) return;
    startBtn.disabled = true;

    navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false })
      .then(function (s) {
        stream = s;
        video.srcObject = s;
        return video.play();
      })
      .then(loadSessions)
      .then(function () {
        running = true;
        startBtn.hidden = true;
        say('Warming up…', 'busy');
        step();
      })
      .catch(function (err) {
        startBtn.disabled = false;
        var msg = err && err.name === 'NotAllowedError'
          ? 'Camera permission refused. Allow it in the address bar to run the bench.'
          : (err && err.message) || String(err);
        say(msg, 'bad');
      });
  }

  function stop() {
    running = false;
    if (stream) {
      stream.getTracks().forEach(function (t) { t.stop(); });
      stream = null;
    }
    if (video) video.srcObject = null;
    if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (startBtn) { startBtn.hidden = false; startBtn.disabled = false; }
    lastMs = 0;
    say('Camera released.', '');
  }

  function open() {
    panel.hidden = false;
    document.body.classList.add('bench-open');
    startBtn.focus();
  }

  function close() {
    stop();
    panel.hidden = true;
    document.body.classList.remove('bench-open');
    var opener = $('bench');
    if (opener) opener.focus();
  }

  function init() {
    panel = $('benchPanel');
    if (!panel) return;
    video = $('benchVideo');
    canvas = $('benchCanvas');
    statusEl = $('benchStatus');
    listEl = $('benchList');
    startBtn = $('benchStart');
    ctx = canvas.getContext('2d');

    work = document.createElement('canvas');
    work.width = work.height = INPUT;
    wctx = work.getContext('2d', { willReadFrequently: true });

    $('bench').addEventListener('click', open);
    $('benchClose').addEventListener('click', close);
    startBtn.addEventListener('click', start);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !panel.hidden) { e.stopPropagation(); close(); }
    }, true);

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      startBtn.disabled = true;
      say('This browser does not expose a camera to the page.', 'bad');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { open: open, close: close, stop: stop };
})();
