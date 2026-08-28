/* The search area.
 *
 * Not a slippy map — a survey grid, because that is the vocabulary a rescue team calls
 * over the radio. Cell B3 on this screen is cell B3 in the callout, in the risk ledger
 * and in the route. The cell fill is the hazard field the route planner actually costs
 * against, so the operator can see why a route bent around something.
 */
window.MapView = (function () {
  var MARGIN = { l: 26, t: 20, r: 12, b: 12 };

  function layout(w, h, cols, rows) {
    var aw = w - MARGIN.l - MARGIN.r, ah = h - MARGIN.t - MARGIN.b;
    var cell = Math.min(aw / cols, ah / rows);
    return {
      cell: cell,
      ox: MARGIN.l + (aw - cell * cols) / 2,
      oy: MARGIN.t + (ah - cell * rows) / 2
    };
  }

  function draw(canvas, state, t) {
    var f = RESQ.fit(canvas), ctx = f.ctx, w = f.w, h = f.h;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#0A0D0E';
    ctx.fillRect(0, 0, w, h);

    var g = (state && state.grid) || { cols: 'ABCDEFGH'.split(''), rows: 6, cell_m: 3 };
    var cols = g.cols.length, rows = g.rows;
    var L = layout(w, h, cols, rows);
    var field = (state && state.hazard_field) || {};
    var swept = ((state && state.swept) || []).reduce(function (a, z) { a[z] = 1; return a; }, {});

    function cellXY(ci, ri) { return [L.ox + ci * L.cell, L.oy + (rows - 1 - ri) * L.cell]; }
    function metresXY(x, y) {
      return [L.ox + (x / g.cell_m) * L.cell, L.oy + (rows - y / g.cell_m) * L.cell];
    }
    function zoneCenter(zone) {
      var ci = g.cols.indexOf(zone[0]), ri = parseInt(zone.slice(1), 10) - 1;
      var p = cellXY(ci < 0 ? 0 : ci, isNaN(ri) ? 0 : ri);
      return [p[0] + L.cell / 2, p[1] + L.cell / 2];
    }

    // Cells: hazard fill, swept marker, hairline.
    for (var ri = 0; ri < rows; ri++) {
      for (var ci = 0; ci < cols; ci++) {
        var zone = g.cols[ci] + (ri + 1);
        var p = cellXY(ci, ri);
        var risk = field[zone] || 0;
        if (risk > 1) {
          ctx.fillStyle = RESQ.ramp(risk, Math.min(0.55, 0.06 + risk / 190));
          ctx.fillRect(p[0], p[1], L.cell, L.cell);
        } else if (swept[zone]) {
          ctx.fillStyle = 'rgba(231,234,232,0.06)';
          ctx.fillRect(p[0], p[1], L.cell, L.cell);
        }
        ctx.strokeStyle = 'rgba(54,67,71,0.75)';
        ctx.lineWidth = 1;
        ctx.strokeRect(Math.round(p[0]) + 0.5, Math.round(p[1]) + 0.5, L.cell, L.cell);
      }
    }

    // Axis labels — the shared vocabulary.
    ctx.font = '500 10px "IBM Plex Mono", ui-monospace, monospace';
    ctx.fillStyle = '#5E6A6E';
    ctx.textAlign = 'center';
    for (var c2 = 0; c2 < cols; c2++) {
      ctx.fillText(g.cols[c2], L.ox + c2 * L.cell + L.cell / 2, L.oy - 7);
    }
    ctx.textAlign = 'right';
    for (var r2 = 0; r2 < rows; r2++) {
      ctx.fillText(String(r2 + 1), L.ox - 7, cellXY(0, r2)[1] + L.cell / 2 + 3.5);
    }
    ctx.textAlign = 'left';

    // North, so a printed grid and a compass agree.
    ctx.strokeStyle = '#5E6A6E';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(w - 18, L.oy + 22); ctx.lineTo(w - 18, L.oy + 4);
    ctx.moveTo(w - 22, L.oy + 9); ctx.lineTo(w - 18, L.oy + 4); ctx.lineTo(w - 14, L.oy + 9);
    ctx.stroke();
    ctx.fillStyle = '#5E6A6E';
    ctx.font = '500 9px "IBM Plex Mono", ui-monospace, monospace';
    ctx.fillText('N', w - 21, L.oy + 32);

    if (!state || !state.connected) {
      ctx.fillStyle = '#5E6A6E';
      ctx.font = '600 14px "Barlow Condensed", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('AWAITING TELEMETRY', w / 2, h - 4);
      ctx.textAlign = 'left';
      return;
    }

    var route = state.route;

    function drawPath(path, color, dashed, width) {
      if (!path || path.length < 2) return;
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      if (dashed) ctx.setLineDash([5, 5]);
      ctx.beginPath();
      path.forEach(function (z, i) {
        var p = zoneCenter(z);
        if (i === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]);
      });
      ctx.stroke();
      ctx.restore();
    }

    if (route && route.reachable) {
      if (!route.identical && route.chosen === 'B' && route.fastest) {
        drawPath(route.fastest.path, 'rgba(94,106,110,0.9)', true, 1.5);
      }
      var rec = route.recommended;
      drawPath(rec.path, '#3FBF6A', false, 2.5);
      rec.path.forEach(function (z, i) {
        if (i === 0 || i === rec.path.length - 1) return;
        var p = zoneCenter(z);
        ctx.fillStyle = '#3FBF6A';
        ctx.fillRect(p[0] - 1.5, p[1] - 1.5, 3, 3);
      });
    }

    // Hazards, one marker per cell — several hazards in one cell is one place to avoid,
    // not three overlapping diamonds.
    var byZone = {};
    (state.hazards || []).forEach(function (hz) {
      (byZone[hz.zone] = byZone[hz.zone] || []).push(hz);
    });
    var SHORT = { fire: 'FIRE', smoke: 'SMOKE', debris: 'DEBRIS', gas: 'GAS', co: 'CO', heat: 'HEAT' };
    var taken = [];                       // label boxes already drawn, to avoid pile-ups
    var marks = Object.keys(byZone).map(function (zone) {
      var group = byZone[zone].slice().sort(function (a, b) { return b.severity - a.severity; });
      return { zone: zone, worst: group[0], count: group.length };
    }).sort(function (a, b) { return b.worst.severity - a.worst.severity; });

    marks.forEach(function (m) {
      var p = zoneCenter(m.zone);
      var s = Math.max(7, L.cell * 0.22);
      ctx.save();
      ctx.translate(p[0], p[1]);
      ctx.rotate(Math.PI / 4);
      ctx.fillStyle = RESQ.ramp(m.worst.severity, 0.92);
      ctx.fillRect(-s / 2, -s / 2, s, s);
      ctx.restore();
      m.p = p; m.s = s;
    });

    // Reserve the rover's own footprint first: a hazard label printed under the rover
    // marker hides the one thing the operator is tracking.
    var rpose = state.pose || { x: 0, y: 0 };
    var rpt = metresXY(rpose.x, rpose.y);
    var guard = Math.max(10, L.cell * 0.3);
    taken.push([rpt[0] - guard, rpt[1] - guard, rpt[0] + guard, rpt[1] + guard]);

    ctx.font = '500 9px "IBM Plex Mono", ui-monospace, monospace';
    ctx.textAlign = 'center';
    marks.forEach(function (m) {
      var text = SHORT[m.worst.kind] || m.worst.label.toUpperCase();
      if (m.count > 1) text += '+' + (m.count - 1);
      var half = ctx.measureText(text).width / 2 + 3;
      var box = [m.p[0] - half, m.p[1] + m.s + 2, m.p[0] + half, m.p[1] + m.s + 13];
      var clash = taken.some(function (b) {
        return !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]);
      });
      if (clash) return;
      taken.push(box);
      ctx.fillStyle = RESQ.ramp(m.worst.severity);
      ctx.fillText(text, m.p[0], m.p[1] + m.s + 11);
    });
    ctx.textAlign = 'left';

    // Where the rover has been.
    var track = state.track || [];
    if (track.length > 1) {
      ctx.strokeStyle = 'rgba(231,234,232,0.22)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      track.forEach(function (pt, i) {
        var p = metresXY(pt.x, pt.y);
        if (i === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]);
      });
      ctx.stroke();
    }

    // Survivors — ring thickness is confidence, so a weak contact looks weak.
    (state.survivors || []).forEach(function (s) {
      var p = zoneCenter(s.zone);
      var r = Math.max(8, L.cell * 0.24);
      var alpha = s.stale ? 0.35 : 1;
      ctx.save();
      ctx.globalAlpha = alpha;
      if (!s.stale && s.confidence >= 0.85) {
        var pulse = 1 + 0.14 * Math.sin(t / 320);
        ctx.strokeStyle = 'rgba(255,59,48,0.35)';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(p[0], p[1], r * 1.8 * pulse, 0, Math.PI * 2); ctx.stroke();
      }
      ctx.beginPath();
      ctx.arc(p[0], p[1], r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255,59,48,0.16)';
      ctx.fill();
      ctx.strokeStyle = RESQ.confidenceColor(s.confidence);
      ctx.lineWidth = 1 + 3 * s.confidence;
      ctx.stroke();
      ctx.fillStyle = '#FFF';
      ctx.font = '600 12px "Barlow Condensed", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(s.id, p[0], p[1] + 4);
      ctx.font = '500 9px "IBM Plex Mono", ui-monospace, monospace';
      ctx.fillStyle = RESQ.confidenceColor(s.confidence);
      ctx.fillText(Math.round(s.confidence * 100) + '%', p[0], p[1] - r - 5);
      ctx.textAlign = 'left';
      ctx.restore();
    });

    // The rover itself.
    var pose = state.pose || { x: 0, y: 0, heading: 0 };
    var rp = metresXY(pose.x, pose.y);
    var size = Math.max(7, L.cell * 0.2);
    ctx.save();
    ctx.translate(rp[0], rp[1]);
    ctx.rotate((-pose.heading + 90) * Math.PI / 180);
    ctx.beginPath();
    ctx.moveTo(0, -size);
    ctx.lineTo(size * 0.72, size * 0.75);
    ctx.lineTo(0, size * 0.35);
    ctx.lineTo(-size * 0.72, size * 0.75);
    ctx.closePath();
    ctx.fillStyle = state.estop ? '#FF3B30' : '#E7EAE8';
    ctx.strokeStyle = '#0A0D0E';        // a halo, so the rover stays findable over a hazard
    ctx.lineWidth = 2.5;
    ctx.stroke();
    ctx.fill();
    ctx.restore();
  }

  return { draw: draw };
})();
