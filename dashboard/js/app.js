/* Dashboard wiring.
 *
 * One websocket in, one render out. The server sends a complete MissionState roughly
 * eight times a second; nothing here computes risk, fusion or routes, so the screen and
 * the log can never disagree about what was decided.
 */
(function () {
  var state = null;
  var socket = null;
  var retry = 0;
  var auth = { required: false, canCommand: true };
  var TOKEN_KEY = 'resq.operator.token';

  var $ = function (id) { return document.getElementById(id); };

  /* Only touch the DOM when what it shows has actually changed.
   *
   * The server sends a full state eight times a second. Rebuilding the action list and
   * the log at that rate is wasted work, and both are aria-live regions -- a screen
   * reader would read them aloud eight times a second, which makes the dashboard
   * unusable for the person it is meant to help. Keys round away the noise so a reading
   * that wobbles in the third decimal does not count as a change.
   */
  var lastKeys = {};
  function changed(name, key) {
    if (lastKeys[name] === key) return false;
    lastKeys[name] = key;
    return true;
  }
  function keyOf(v) { return JSON.stringify(v); }

  /* ── connection ──────────────────────────────────────────────────────── */

  function connect() {
    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket = new WebSocket(proto + '//' + location.host + '/ws/dashboard');

    socket.onopen = function () {
      retry = 0;
      var saved = safeGet(TOKEN_KEY);
      if (saved) socket.send(JSON.stringify({ cmd: 'auth', token: saved }));
    };
    socket.onmessage = function (ev) {
      var msg = JSON.parse(ev.data);
      if (msg.type === 'state') { state = msg.state; paint(); return; }
      if (msg.type === 'hello') {
        auth.required = !!msg.auth_required;
        auth.canCommand = !!msg.can_command;
        paintLock();
        return;
      }
      if (msg.type === 'denied') { flashLock(msg.reason); }
    };
    socket.onclose = function () {
      state = null;
      paint();
      retry = Math.min(retry + 1, 6);
      setTimeout(connect, 400 * retry);
    };
    socket.onerror = function () { try { socket.close(); } catch (e) {} };
  }

  function send(msg) {
    if (socket && socket.readyState === 1) socket.send(JSON.stringify(msg));
  }

  /* Storage can throw outright in a locked-down browser, and a dashboard that will not
     render because it could not read a preference is worse than one that forgets it. */
  function safeGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function safeSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* fine */ } }

  /* ── operator lock ───────────────────────────────────────────────────── */

  var lock = $('lock'), unlockBtn = $('unlock'), keyInput = $('opkey');

  function paintLock() {
    var locked = auth.required && !auth.canCommand;
    lock.hidden = !auth.required;
    if (auth.required && auth.canCommand) lock.hidden = true;

    Array.prototype.forEach.call(document.querySelectorAll('.mode'), function (b) {
      b.disabled = locked;
      b.title = locked ? 'Unlock the controls to change mode.' : '';
    });
    estopBtn.disabled = locked;
    estopBtn.title = locked
      ? 'Unlock the controls to stop the rover.'
      : 'Stop the rover immediately. Esc does the same from anywhere.';
  }

  function flashLock(reason) {
    unlockBtn.textContent = reason ? 'Controls locked' : 'Unlock controls';
    setTimeout(function () { unlockBtn.textContent = 'Unlock controls'; }, 2500);
  }

  unlockBtn.addEventListener('click', function () {
    if (keyInput.hidden) {
      keyInput.hidden = false;
      keyInput.focus();
      unlockBtn.textContent = 'Submit key';
    } else {
      submitKey();
    }
  });

  lock.addEventListener('submit', function (e) { e.preventDefault(); submitKey(); });

  function submitKey() {
    var value = keyInput.value.trim();
    if (!value) { keyInput.focus(); return; }
    safeSet(TOKEN_KEY, value);
    send({ cmd: 'auth', token: value });
    keyInput.value = '';
    keyInput.hidden = true;
    unlockBtn.textContent = 'Unlock controls';
  }

  /* ── controls ────────────────────────────────────────────────────────── */

  var estopBtn = $('estop');
  var estopLabel = estopBtn.querySelector('.estop__label');
  var armTimer = null;

  function disarm() {
    clearTimeout(armTimer);
    armTimer = null;
    estopBtn.classList.remove('is-arming');
  }

  estopBtn.addEventListener('click', function () {
    if (!(state && state.estop)) {
      send({ cmd: 'estop', on: true });       // stopping is always immediate
      return;
    }
    // Releasing lets the rover move again. That gets a second press, and the armed
    // state times out on its own so a stray click cannot leave it primed.
    if (armTimer) {
      disarm();
      send({ cmd: 'estop', on: false });
    } else {
      estopBtn.classList.add('is-arming');
      estopLabel.textContent = 'Press again to release';
      armTimer = setTimeout(function () {
        disarm();
        estopLabel.textContent = 'Release rover';
      }, 4000);
    }
  });

  Array.prototype.forEach.call(document.querySelectorAll('.mode'), function (btn) {
    btn.addEventListener('click', function () {
      send({ cmd: 'mode', mode: btn.dataset.mode });
    });
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (auth.required && !auth.canCommand) return;
    if (!(state && state.estop)) send({ cmd: 'estop', on: true });
  });

  /* ── gauges ──────────────────────────────────────────────────────────── */

  var GAUGES = [
    { key: 'temp_c', name: 'Temp', unit: '°C', limit: '38\u00A0°C limit', dp: 0,
      level: function (v) { return v >= 55 ? 'crit' : v >= 45 ? 'bad' : v >= 38 ? 'warn' : 'ok'; } },
    { key: 'co_ppm', name: 'CO', unit: 'ppm', limit: '35\u00A0ppm limit', dp: 0,
      level: function (v) { return v >= 400 ? 'crit' : v >= 200 ? 'bad' : v >= 35 ? 'warn' : 'ok'; } },
    { key: 'lel_pct', name: 'Gas', unit: '% LEL', limit: 'evac at 10%\u00A0LEL', dp: 0,
      level: function (v) { return v >= 25 ? 'crit' : v >= 10 ? 'bad' : v >= 5 ? 'warn' : 'ok'; } },
    { key: 'o2_pct', name: 'Oxygen', unit: '%', limit: '19.5–23.5%', dp: 1,
      level: function (v) { return v < 18 || v > 24 ? 'crit' : (v < 19.5 || v > 23.5) ? 'bad' : v < 20.4 ? 'warn' : 'ok'; } },
    { key: 'pm25_ugm3', name: 'Smoke', unit: 'µg/m³', limit: '150\u00A0µg/m³', dp: 0,
      level: function (v) { return v >= 500 ? 'crit' : v >= 250 ? 'bad' : v >= 150 ? 'warn' : 'ok'; } }
  ];

  function paintGauges(atmo) {
    var host = $('gauges');
    host.innerHTML = '';
    GAUGES.forEach(function (g) {
      var v = atmo ? atmo[g.key] : null;
      var el = document.createElement('dl');
      el.className = 'gauge';
      el.dataset.level = (v === null || v === undefined) ? 'none' : g.level(v);
      var dt = document.createElement('dt');
      dt.textContent = g.name;
      var dd = document.createElement('dd');
      if (v === null || v === undefined) {
        dd.textContent = 'not measured';
      } else {
        dd.textContent = v.toFixed(g.dp);
        var u = document.createElement('span');
        u.className = 'unit';
        u.textContent = g.unit;
        dd.appendChild(u);
      }
      el.appendChild(dt);
      el.appendChild(dd);
      if (g.limit) {
        var lim = document.createElement('span');
        lim.className = 'limit';
        lim.textContent = g.limit;
        dd.appendChild(lim);
      }
      host.appendChild(el);
    });
  }

  /* ── lists ───────────────────────────────────────────────────────────── */

  function paintDetections(dets, thermal) {
    var host = $('dets');
    host.innerHTML = '';
    if (!dets || !dets.length) {
      host.innerHTML = '<li class="empty">Nothing in view.</li>';
      return;
    }
    dets.slice().sort(function (a, b) { return b.conf - a.conf; }).forEach(function (d) {
      var li = document.createElement('li');
      li.style.color = RESQ.classColor(d.cls);
      li.innerHTML =
        '<span class="cls">' + d.cls + (d.track_id ? '<small>' + d.track_id + '</small>' : '') + '</span>' +
        '<span class="meter"><i style="width:' + Math.round(d.conf * 100) + '%"></i></span>' +
        '<span class="pct">' + Math.round(d.conf * 100) + '%</span>';
      if (d.cls === 'person') {
        var note = document.createElement('span');
        note.className = 'corr';
        note.textContent = thermal && thermal.available
          ? 'Cross-checked against thermal.'
          : 'Camera only — thermal is offline.';
        li.appendChild(note);
      }
      host.appendChild(li);
    });
  }

  function paintSurvivors(survivors) {
    var host = $('survivors');
    host.innerHTML = '';
    if (!survivors || !survivors.length) {
      host.innerHTML = '<li class="empty">No contacts yet. The sweep is still running.</li>';
      return;
    }
    survivors.forEach(function (s) {
      var li = document.createElement('li');
      if (s.stale) li.className = 'sv--stale';

      var top = document.createElement('div');
      top.className = 'sv__top';
      top.innerHTML =
        '<span class="sv__rank">' + s.rank + '</span>' +
        '<span class="sv__id">Survivor ' + s.id + '</span>' +
        '<span class="sv__zone">' + s.zone + '</span>' +
        '<span class="sv__fix">' + (s.range_m !== undefined ? s.range_m + '\u00A0m from ' + s.seen_from : '') + '</span>' +
        '<span class="sv__tier" style="color:' + RESQ.bandColor(s.tier) + '">' + s.tier + '</span>' +
        '<span class="sv__conf" style="color:' + RESQ.confidenceColor(s.confidence) + '">' +
          Math.round(s.confidence * 100) + '%</span>';
      li.appendChild(top);

      var bar = document.createElement('div');
      bar.className = 'sv__bar';
      bar.innerHTML = '<i style="width:' + Math.round(s.confidence * 100) + '%;background:' +
        RESQ.confidenceColor(s.confidence) + '"></i>';
      li.appendChild(bar);

      var why = document.createElement('div');
      why.className = 'sv__why';
      (s.terms || []).filter(function (t) { return t.source !== 'prior'; }).forEach(function (t) {
        var chip = document.createElement('span');
        chip.className = t.delta > 0.25 ? 'is-pos' : (t.delta < -0.25 ? 'is-neg' : '');
        chip.textContent = t.label + ': ' + t.detail;
        why.appendChild(chip);
      });
      li.appendChild(why);

      if (s.route && s.route.reachable && s.route.recommended) {
        var r = document.createElement('p');
        r.className = 'sv__route';
        r.innerHTML = s.route.recommended.name + ' · <b>' +
          s.route.recommended.path.join(' → ') + '</b> · ' +
          s.route.recommended.distance_m + '\u00A0m';
        li.appendChild(r);
      } else if (s.route && !s.route.reachable) {
        var nr = document.createElement('p');
        nr.className = 'sv__route';
        nr.textContent = 'No route to this cell.';
        li.appendChild(nr);
      }

      host.appendChild(li);
    });
  }

  function paintActions(actions) {
    var host = $('acts');
    host.innerHTML = '';
    if (!actions || !actions.length) {
      host.innerHTML = '<li class="empty">Connect a rover to get a recommendation.</li>';
      return;
    }
    actions.forEach(function (a) {
      var li = document.createElement('li');
      li.dataset.urgency = a.urgency;
      var d = document.createElement('span');
      d.className = 'do';
      d.textContent = a.text;
      var b = document.createElement('span');
      b.className = 'because';
      b.textContent = a.because;
      li.appendChild(d);
      li.appendChild(b);
      host.appendChild(li);
    });
  }

  function paintLog(events) {
    var host = $('log');
    host.innerHTML = '';
    (events || []).slice().reverse().forEach(function (e) {
      var li = document.createElement('li');
      li.dataset.level = e.level;
      var time = document.createElement('time');
      time.textContent = RESQ.clock(e.mission_t);
      var txt = document.createElement('span');
      txt.textContent = e.text;
      li.appendChild(time);
      li.appendChild(txt);
      host.appendChild(li);
    });
  }

  /* Canvases carry no text, so they describe themselves for assistive tech. Updated
     only when the description changes, for the same reason the lists are. */
  function describeCanvases(state, risk) {
    var dets = (state.detections || []).map(function (d) {
      return d.cls + ' ' + Math.round(d.conf * 100) + '%';
    }).join(', ');
    var feedText = state.connected
      ? 'Rover camera view. ' + (dets ? 'Detected: ' + dets + '.' : 'Nothing in view.')
      : 'Rover camera view. No signal.';
    if (changed('feedAlt', feedText)) $('feed').setAttribute('aria-label', feedText);

    var parts = ['Survey grid. Rover in ' + ((state.pose && state.pose.zone) || 'unknown') + '.'];
    (state.survivors || []).forEach(function (s) {
      parts.push('Survivor ' + s.id + ' in ' + s.zone + ' at ' +
                 Math.round(s.confidence * 100) + '% confidence.');
    });
    (state.hazards || []).slice(0, 4).forEach(function (h) {
      parts.push(h.label + ' in ' + h.zone + '.');
    });
    if (state.route && state.route.reachable && state.route.recommended) {
      parts.push('Recommended route: ' + state.route.recommended.path.join(', ') + '.');
    }
    var mapText = state.connected ? parts.join(' ') : 'Survey grid. No telemetry.';
    if (changed('mapAlt', mapText)) $('map').setAttribute('aria-label', mapText);
  }

  /* ── the whole screen ────────────────────────────────────────────────── */

  function paint() {
    var connected = !!(state && state.connected);
    $('banner').hidden = connected;
    $('feedLive').hidden = !connected;

    if (!state) {
      $('roverStatus').textContent = 'no server';
      RiskLedger.render(null);
      return;
    }

    $('missionId').textContent = state.mission_id;
    $('clock').textContent = RESQ.clock(state.mission_t);
    $('zone').textContent = (state.pose && state.pose.zone) || '--';

    var robot = state.robot || {};
    var batt = $('battery');
    batt.textContent = robot.battery_pct === null || robot.battery_pct === undefined
      ? '--' : Math.round(robot.battery_pct) + '%';
    batt.className = 'num' + (robot.battery_pct < 15 ? ' is-bad' : robot.battery_pct < 25 ? ' is-warn' : '');

    var link = $('link');
    link.textContent = robot.link_quality === null || robot.link_quality === undefined
      ? '--' : Math.round(robot.link_quality * 100) + '%';
    link.className = 'num' + (!connected || robot.link_quality < 0.3 ? ' is-bad'
      : robot.link_quality < 0.45 ? ' is-warn' : '');

    $('roverStatus').textContent = connected ? (robot.status || 'unknown') : 'link lost';

    Array.prototype.forEach.call(document.querySelectorAll('.mode'), function (btn) {
      var on = btn.dataset.mode === state.mode;
      btn.classList.toggle('is-on', on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    });

    estopBtn.classList.toggle('is-on', !!state.estop && !armTimer);
    estopBtn.setAttribute('aria-pressed', state.estop ? 'true' : 'false');
    if (!armTimer) {
      estopLabel.textContent = state.estop ? 'Release rover' : 'Stop rover';
      if (!state.estop) disarm();
    }

    $('feedSource').textContent = !connected ? 'no signal'
      : (state.frame_jpeg ? 'rover camera' : 'sim feed · drawn from live sensor values');

    var th = state.thermal || {};
    var tt = $('thermalTag');
    tt.textContent = th.available
      ? 'thermal ' + (th.max_c === null || th.max_c === undefined ? 'on' : th.max_c.toFixed(1) + ' °C peak')
      : 'thermal offline';
    tt.className = 'tag' + (th.available ? ' is-on' : ' is-warn');

    if (changed('dets', keyOf([(state.detections || []).map(function (d) {
      return [d.cls, d.track_id, Math.round(d.conf * 100)];
    }), th.available]))) {
      paintDetections(state.detections, th);
    }

    if (changed('gauges', keyOf(GAUGES.map(function (g) {
      var v = state.atmosphere ? state.atmosphere[g.key] : null;
      return v === null || v === undefined ? null : v.toFixed(g.dp);
    })))) {
      paintGauges(state.atmosphere);
    }

    var unavailable = (state.atmosphere && state.atmosphere.unavailable) || [];
    var atmoTag = $('atmoTag');
    atmoTag.textContent = unavailable.length ? unavailable.join(', ') + ' not measured' : 'all sensors reporting';
    atmoTag.className = 'tag' + (unavailable.length ? ' is-warn' : ' is-on');

    var risk = state.risk;
    var panel = $('risk');
    if (risk) {
      $('riskScore').textContent = Math.round(risk.score);
      $('riskScore').style.color = RESQ.bandColor(risk.band);
      var band = $('riskBand');
      band.textContent = risk.band;
      band.style.color = RESQ.bandColor(risk.band);
      $('riskSay').textContent = risk.summary;
      var entry = $('entryTag');
      entry.textContent = risk.entry_safe ? 'entry conditions acceptable' : 'do not send people in yet';
      entry.className = 'tag' + (risk.entry_safe ? ' is-on' : ' is-bad');
      panel.dataset.state = risk.band === 'CRITICAL' ? 'critical' : risk.band === 'HIGH' ? 'danger' : 'ok';
      $('atmo-panel').dataset.state =
        (state.atmosphere && (state.atmosphere.lel_pct >= 10 || state.atmosphere.co_ppm >= 200
          || state.atmosphere.o2_pct < 19.5)) ? 'danger' : 'ok';
    } else {
      $('riskScore').textContent = '--';
      $('riskBand').textContent = connected ? 'measuring' : 'standby';
      $('riskSay').textContent = 'No rover reporting. Nothing has been measured.';
      $('entryTag').textContent = '';
      panel.dataset.state = 'ok';
    }
    if (changed('ledger', keyOf((risk ? risk.causes : []).map(function (c) {
      return [c.key, c.points.toFixed(0), c.reading];
    })))) {
      RiskLedger.render(state);
    }

    if (changed('survivors', keyOf((state.survivors || []).map(function (s) {
      return [s.id, s.zone, s.rank, s.tier, s.stale, Math.round(s.confidence * 100),
              s.range_m, s.seen_from,
              (s.terms || []).map(function (t) { return t.detail; }),
              s.route && s.route.recommended ? s.route.recommended.path.join() : null];
    })))) {
      paintSurvivors(state.survivors);
    }

    if (changed('acts', keyOf(state.actions))) paintActions(state.actions);

    if (changed('log', keyOf([(state.events || []).length,
                              (state.events || []).map(function (e) { return e.text; })]))) {
      paintLog(state.events);
    }

    describeCanvases(state, risk);
    if (window.Alarm) Alarm.update(state);
  }

  /* ── canvases ────────────────────────────────────────────────────────── */

  var feed = $('feed'), map = $('map');
  function frame(t) {
    var mt = RESQ.stillTime(t);       // frozen clock when the viewer asked for less motion
    FeedView.draw(feed, state, mt);
    MapView.draw(map, state, mt);
    requestAnimationFrame(frame);
  }

  connect();
  paintLock();
  paint();
  /* Fetched once, not broadcast: the mission anchor does not move, so neither does the
     answer, and a shelter list on the 8 Hz socket would be the same three rows forever. */
  if (window.ShelterPanel) ShelterPanel.load();
  requestAnimationFrame(frame);
})();
