/* The risk ledger — the one place this dashboard spends its boldness.
 *
 * A risk gauge that shows only a number tells an incident commander nothing they can
 * argue with. Here the meter *is* the explanation: every cause owns a slice of the
 * column sized by the points it contributed, and the row beside it, aligned to the same
 * height, names the reading and the limit it crossed. The column fills from the bottom,
 * biggest driver first, so the thing to fix is always at the base.
 *
 * Fill encodes the kind of cause, not just its size:
 *   solid ramp  — a hazard, hotter is worse
 *   hatched     — a reason to go in anyway (a survivor), or a sensor that is not reading
 *   grey        — the rover's own condition
 *   flat dim    — the smallest drivers, folded together because the column ran out of room
 */
window.RiskLedger = (function () {
  var bar, list, shown = null, lastColumn = -1;

  /* A row cannot be read below this, so the CSS refuses to draw one shorter (see
     `.ledger__row`). That refusal is also the ledger's capacity limit: a column of H
     pixels holds floor(H / MIN_ROW) rows and not one more. Past that the rows stop
     shrinking, the column-reverse stack grows out of the top of its box, and the labels
     print over the summary sentence above. Fold instead of overflow. */
  var MIN_ROW = 15;

  /* A hazard only appears here once it has crossed its limit, so the ramp starts at
     caution. Nothing on this meter is ever green — green would say "fine". */
  function hazardTone(cause) { return RESQ.ramp(32 + cause.severity * 68); }

  function fillFor(cause) {
    if (cause.kind === 'hazard') return { background: hazardTone(cause) };
    if (cause.kind === 'urgency') {
      return {
        background: 'repeating-linear-gradient(-45deg,#E7EAE8 0 3px,#0E1113 3px 6px)'
      };
    }
    if (cause.kind === 'unknown') {
      return {
        background: 'repeating-linear-gradient(-45deg,#5E6A6E 0 2px,#14181A 2px 6px)'
      };
    }
    if (cause.kind === 'rest') return { background: '#39434B' };
    return { background: '#5E6A6E' };
  }

  function textFor(cause) {
    if (cause.kind === 'hazard') return hazardTone(cause);
    if (cause.kind === 'urgency') return '#E7EAE8';
    if (cause.kind === 'rest') return '#5E6A6E';
    return '#97A2A5';
  }

  /* Everything the column has no room to name gets one row and one slice between them,
     carrying the points of all of them. The meter still adds up to the score — which is
     the only promise it makes — and nothing is drawn in a size it cannot be read at. */
  function foldToFit(causes, column) {
    if (!column) return causes.slice();                 // not laid out yet; measure later
    var capacity = Math.max(1, Math.floor(column / MIN_ROW));
    if (causes.length <= capacity) return causes.slice();

    var keep = causes.slice(0, capacity - 1);           // capacity 1 keeps nothing: all fold
    var rest = causes.slice(capacity - 1);
    var points = rest.reduce(function (a, c) { return a + c.points; }, 0);

    keep.push({
      key: '_rest', kind: 'rest', points: points, severity: 0,
      label: rest.length + (keep.length ? ' more drivers' : ' drivers'),
      reading: rest.map(function (c) { return c.label; }).join(', '),
      threshold: null
    });
    return keep;
  }

  function render(state) {
    bar = bar || document.getElementById('ledgerBar');
    list = list || document.getElementById('ledgerList');
    var ticks = bar.querySelector('.ledger__ticks');

    shown = state || null;
    var risk = (state && state.risk) || null;
    bar.querySelectorAll('.ledger__seg').forEach(function (n) { n.remove(); });
    list.innerHTML = '';

    if (!risk || !risk.causes.length) {
      lastColumn = -1;
      var gap = document.createElement('div');
      gap.className = 'ledger__seg ledger__seg--gap';
      gap.style.flex = '100 0 0';
      bar.insertBefore(gap, ticks);
      var li = document.createElement('li');
      li.className = 'ledger__empty';
      li.textContent = state && state.connected
        ? 'Nothing measured is dangerous. All sensors reporting.'
        : 'No readings yet.';
      list.appendChild(li);
      return;
    }

    /* Measured, not assumed: on a short window this column is a few dozen pixels, and
       how many causes it can name — and whether any of them can carry a second line —
       are both answers in pixels. */
    var column = list.clientHeight || 0;
    lastColumn = column;
    var causes = foldToFit(risk.causes, column);

    /* How tall each row will actually be, in pixels, before it is built.
     *
     * Row height is proportional to the points a cause contributed -- that is the whole
     * idea, the row is the slice. So whether a row can carry two lines of text is a
     * question about pixels, not about points: four small causes of similar size, which
     * is exactly what a rover with no gas sensor produces, each get a thin band that a
     * label and a reading cannot both fit inside. Deciding on points alone let them
     * overflow and print on top of each other. */
    var shares = causes.map(function (c) {
      return Math.max(1.6, c.points);                // a 0.4-point cause still needs a line
    });
    var total = Math.max(100, shares.reduce(function (a, b) { return a + b; }, 0));
    var pxFor = function (share) { return column ? column * share / total : 999; };

    var used = 0;
    causes.forEach(function (c, i) {
      var share = shares[i];
      used += share;

      var seg = document.createElement('div');
      seg.className = 'ledger__seg';
      seg.style.flex = share + ' 0 0';
      Object.assign(seg.style, fillFor(c));
      bar.insertBefore(seg, ticks);

      // 30 px carries a label and its reading; 17 px carries the label alone.
      var px = pxFor(share);
      var row = document.createElement('li');
      row.className = 'ledger__row'
        + (c.kind === 'rest' ? ' ledger__row--rest' : '')
        + (px < 30 ? ' ledger__row--tight' : '')
        + (px < 17 ? ' ledger__row--micro' : '');
      row.style.flex = share + ' 0 0';

      var body = document.createElement('div');
      body.className = 'ledger__body';

      var label = document.createElement('div');
      label.className = 'ledger__label';
      label.style.color = textFor(c);
      label.textContent = c.label;

      var read = document.createElement('div');
      read.className = 'ledger__read';
      read.textContent = c.threshold ? c.reading + '  ·  ' + c.threshold : c.reading;

      body.appendChild(label);
      body.appendChild(read);

      var pts = document.createElement('span');
      pts.className = 'ledger__pts';
      pts.textContent = '+' + (c.points < 10 ? c.points.toFixed(1) : c.points.toFixed(0));

      row.appendChild(body);
      row.appendChild(pts);
      list.appendChild(row);
    });

    var slack = Math.max(0, 100 - used);
    var pad = document.createElement('div');
    pad.className = 'ledger__seg ledger__seg--gap';
    pad.style.flex = slack + ' 0 0';
    bar.insertBefore(pad, ticks);

    var padRow = document.createElement('li');
    padRow.className = 'ledger__row ledger__row--gap';
    padRow.style.flex = slack + ' 0 0';
    list.appendChild(padRow);
  }

  /* The dashboard repaints the ledger when the causes change, which is the only thing it
     can know about. How much room the ledger has is the other half of the layout and it
     changes on its own — a resized window, a panel above it growing a line. Re-measure
     when the box does, or a column that was tall enough when it was drawn keeps drawing
     rows it can no longer hold. */
  if (window.ResizeObserver) {
    new ResizeObserver(function (entries) {
      var h = Math.round(entries[0].contentRect.height);
      if (h === lastColumn || !shown) return;
      lastColumn = h;
      render(shown);
    }).observe(document.getElementById('ledgerList'));
  }

  return { render: render };
})();
