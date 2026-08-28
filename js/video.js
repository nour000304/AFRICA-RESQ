/* The feed panel.
 *
 * A real rover sends `frame_jpeg` and we draw that. Without one — the simulator, or a
 * camera that dropped out — we draw a synthetic interior built from the same numbers
 * the sensors are reporting: smoke thickens with particulate load, fire glows where the
 * fire detection sits, a figure stands inside the person box. The panel says SIM FEED
 * whenever the picture is drawn rather than photographed, because an operator must
 * never mistake a reconstruction for a photograph.
 */
window.FeedView = (function () {
  var img = new Image();
  var imgReady = false, imgSrc = null;

  function drawPhoto(ctx, w, h, src) {
    if (src !== imgSrc) {
      imgSrc = src; imgReady = false;
      img.onload = function () { imgReady = true; };
      img.src = src;
    }
    if (!imgReady) { ctx.fillStyle = '#07090A'; ctx.fillRect(0, 0, w, h); return; }
    var s = Math.max(w / img.width, h / img.height);
    var dw = img.width * s, dh = img.height * s;
    ctx.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh);
  }

  function drawRoom(ctx, w, h, t, state) {
    var atmo = (state && state.atmosphere) || {};
    var smoke = Math.max(0, Math.min(1, (atmo.pm25_ugm3 || 0) / 700));
    var vx = w * 0.52, vy = h * 0.46;   // vanishing point

    ctx.fillStyle = '#0A0C0D';
    ctx.fillRect(0, 0, w, h);

    // Floor and ceiling receding to the vanishing point.
    ctx.strokeStyle = 'rgba(120,138,142,0.16)';
    ctx.lineWidth = 1;
    for (var i = -6; i <= 6; i++) {
      ctx.beginPath();
      ctx.moveTo(vx + i * w * 0.24, h * 1.15);
      ctx.lineTo(vx, vy);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(vx + i * w * 0.24, -h * 0.15);
      ctx.lineTo(vx, vy);
      ctx.stroke();
    }
    for (var r = 1; r <= 7; r++) {
      var yy = vy + Math.pow(r / 7, 2.1) * (h - vy) * 1.05;
      ctx.globalAlpha = 0.5;
      ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(w, yy); ctx.stroke();
      ctx.globalAlpha = 1;
    }

    // Rubble: fixed shapes, so the scene reads as a place rather than static.
    ctx.fillStyle = 'rgba(28,34,36,0.95)';
    for (var k = 0; k < 14; k++) {
      var bx = RESQ.hash(k * 3.1) * w;
      var by = vy + Math.pow(RESQ.hash(k * 5.7), 1.6) * (h - vy) * 0.95;
      var bw = 20 + RESQ.hash(k * 7.3) * 90 * (by / h);
      var bh = 8 + RESQ.hash(k * 11.9) * 34 * (by / h);
      ctx.beginPath();
      ctx.moveTo(bx, by);
      ctx.lineTo(bx + bw * 0.7, by - bh);
      ctx.lineTo(bx + bw, by - bh * 0.35);
      ctx.lineTo(bx + bw * 0.85, by + bh * 0.4);
      ctx.closePath();
      ctx.fill();
    }

    // A figure inside the person box, so the detection has a subject.
    var person = (state && state.detections || []).filter(function (d) { return d.cls === 'person'; })[0];
    if (person && person.bbox) {
      var px = person.bbox[0] * w, py = person.bbox[1] * h;
      var pw = person.bbox[2] * w, ph = person.bbox[3] * h;
      ctx.fillStyle = 'rgba(46,54,57,0.98)';
      ctx.beginPath();
      ctx.ellipse(px + pw * 0.5, py + ph * 0.13, pw * 0.20, ph * 0.11, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(px + pw * 0.28, py + ph);
      ctx.lineTo(px + pw * 0.34, py + ph * 0.26);
      ctx.lineTo(px + pw * 0.68, py + ph * 0.26);
      ctx.lineTo(px + pw * 0.76, py + ph);
      ctx.closePath();
      ctx.fill();
    }

    // Fire glow behind the flame detection.
    var fire = (state && state.detections || []).filter(function (d) { return d.cls === 'fire'; })[0];
    if (fire && fire.bbox) {
      var fx = (fire.bbox[0] + fire.bbox[2] / 2) * w;
      var fy = (fire.bbox[1] + fire.bbox[3] / 2) * h;
      var rad = Math.max(fire.bbox[2] * w, fire.bbox[3] * h);
      var flicker = 0.72 + 0.28 * Math.sin(t / 90) * Math.sin(t / 37);
      var g = ctx.createRadialGradient(fx, fy, 2, fx, fy, rad);
      g.addColorStop(0, 'rgba(255,196,80,' + (0.75 * flicker).toFixed(3) + ')');
      g.addColorStop(0.35, 'rgba(255,110,25,' + (0.42 * flicker).toFixed(3) + ')');
      g.addColorStop(1, 'rgba(255,60,10,0)');
      ctx.fillStyle = g;
      ctx.fillRect(fx - rad, fy - rad, rad * 2, rad * 2);
    }

    // Smoke: slow drifting layers, thickness driven by the particulate reading.
    if (smoke > 0.02) {
      for (var s2 = 0; s2 < 7; s2++) {
        var cx = ((RESQ.hash(s2 * 13.7) * 1.6 - 0.3) * w + t * (0.006 + s2 * 0.002) * w) % (w * 1.6) - w * 0.3;
        var cy = vy * (0.25 + RESQ.hash(s2 * 3.3) * 0.9) + Math.sin(t / 900 + s2) * 12;
        var rr = w * (0.16 + RESQ.hash(s2 * 9.1) * 0.22);
        var gg = ctx.createRadialGradient(cx, cy, 0, cx, cy, rr);
        var a = 0.16 * smoke * (0.6 + RESQ.hash(s2 * 2.2) * 0.6);
        gg.addColorStop(0, 'rgba(168,176,178,' + a.toFixed(3) + ')');
        gg.addColorStop(1, 'rgba(168,176,178,0)');
        ctx.fillStyle = gg;
        ctx.fillRect(cx - rr, cy - rr, rr * 2, rr * 2);
      }
      ctx.fillStyle = 'rgba(150,160,162,' + (0.10 * smoke).toFixed(3) + ')';
      ctx.fillRect(0, 0, w, h);
    }

    // Vignette, so the overlay stays legible at the edges.
    var v = ctx.createRadialGradient(w / 2, h / 2, h * 0.25, w / 2, h / 2, h * 0.95);
    v.addColorStop(0, 'rgba(0,0,0,0)');
    v.addColorStop(1, 'rgba(0,0,0,0.55)');
    ctx.fillStyle = v;
    ctx.fillRect(0, 0, w, h);
  }

  function reticle(ctx, x, y, bw, bh, color, arm) {
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    var a = Math.min(arm, bw / 2, bh / 2);
    var corners = [[x, y, 1, 1], [x + bw, y, -1, 1], [x, y + bh, 1, -1], [x + bw, y + bh, -1, -1]];
    corners.forEach(function (c) {
      ctx.beginPath();
      ctx.moveTo(c[0] + c[2] * a, c[1]);
      ctx.lineTo(c[0], c[1]);
      ctx.lineTo(c[0], c[1] + c[3] * a);
      ctx.stroke();
    });
  }

  function label(ctx, x, y, text, color) {
    ctx.font = '500 11px "IBM Plex Mono", ui-monospace, monospace';
    var pad = 5, tw = ctx.measureText(text).width;
    ctx.fillStyle = 'rgba(7,9,10,0.82)';
    ctx.fillRect(x, y - 15, tw + pad * 2, 16);
    ctx.fillStyle = color;
    ctx.fillRect(x, y - 15, 2, 16);
    ctx.fillText(text, x + pad, y - 3.5);
  }

  function draw(canvas, state, t) {
    var f = RESQ.fit(canvas), ctx = f.ctx, w = f.w, h = f.h;
    ctx.clearRect(0, 0, w, h);

    if (state && state.frame_jpeg) drawPhoto(ctx, w, h, state.frame_jpeg);
    else drawRoom(ctx, w, h, t, state);

    if (!state || !state.connected) {
      ctx.fillStyle = 'rgba(7,9,10,0.72)';
      ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = '#5E6A6E';
      ctx.font = '600 15px "Barlow Condensed", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('NO SIGNAL', w / 2, h / 2);
      ctx.textAlign = 'left';
      return;
    }

    // Thermal blobs first, underneath the vision boxes.
    var th = state.thermal || {};
    if (th.available) {
      (th.blobs || []).forEach(function (b, i) {
        var x = b.bbox[0] * w, y = b.bbox[1] * h, bw = b.bbox[2] * w, bh = b.bbox[3] * h;
        var hot = RESQ.ramp(Math.min(100, (b.peak_c - 20) * 3.2));
        ctx.save();
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = hot;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(x - 4, y - 4, bw + 8, bh + 8);
        ctx.restore();
        label(ctx, x - 4, y - 6 - (i % 2) * 17, 'THERMAL ' + b.peak_c.toFixed(1) + '°C', hot);
      });
    }

    (state.detections || []).forEach(function (d) {
      var color = RESQ.classColor(d.cls);
      var x = d.bbox[0] * w, y = d.bbox[1] * h, bw = d.bbox[2] * w, bh = d.bbox[3] * h;
      reticle(ctx, x, y, bw, bh, color, 16);
      label(ctx, x, y + bh + 17, d.cls.toUpperCase() + ' ' + Math.round(d.conf * 100) + '%', color);
    });

    // Clearance readout, bottom left — the number that decides whether it can pass.
    var front = state.ranges && state.ranges.front_m;
    ctx.font = '500 11px "IBM Plex Mono", ui-monospace, monospace';
    ctx.fillStyle = front !== null && front !== undefined && front < 1.2 ? '#F2C300' : '#97A2A5';
    ctx.fillText('CLEARANCE ' + (front === null || front === undefined ? '--' : front.toFixed(1) + '\u00A0m'), 12, h - 12);
  }

  return { draw: draw };
})();
