/* The audible alarm.
 *
 * Ported from the upstream AFRICA RESQ perception loop, which played alert.mp3 on a
 * loop for as long as fire stayed in frame. The sound is kept; the loop is not.
 *
 * An alarm that runs continuously through a two-hour incident gets muted in the first
 * five minutes, and after that it warns nobody about anything. So this one fires on
 * transitions and says one thing: something changed that you need to look at now.
 *
 *   - the risk band crosses into CRITICAL (not while it stays there)
 *   - a new critical entry appears in the mission log -- a survivor confirmed, the
 *     radio link lost, the operator's stop engaged
 *
 * Muting is the operator's, stored per browser, and survives a reload. Browsers block
 * audio until the page has been interacted with, so an alarm that has never been armed
 * says so on the button rather than failing silently.
 */
window.Alarm = (function () {
  var MUTE_KEY = 'resq.alarm.muted';
  var MIN_GAP_MS = 4000;        // never stack two alarms on top of each other

  var audio = null;
  var muted = false;
  var armed = false;            // has a user gesture unblocked playback yet
  var lastBand = null;
  var lastCriticalEvent = null;
  var lastPlayed = 0;
  var button = null;

  function safeGet(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } }
  function safeSet(k, v) { try { window.localStorage.setItem(k, v); } catch (e) {} }

  function label() {
    if (!button) return;
    var text = muted ? 'Alarm off' : armed ? 'Alarm on' : 'Alarm — tap to arm';
    button.textContent = text;
    button.setAttribute('aria-pressed', muted ? 'false' : 'true');
    button.classList.toggle('is-on', !muted && armed);
    button.title = muted
      ? 'The audible alarm is off. Critical changes still appear on screen.'
      : armed ? 'Sounds once when the risk band reaches critical, or on a critical log entry.'
              : 'Your browser blocks sound until you interact with the page. Click to allow it.';
  }

  function play() {
    if (muted || !audio) return;
    var now = Date.now();
    if (now - lastPlayed < MIN_GAP_MS) return;
    lastPlayed = now;
    try { audio.currentTime = 0; } catch (e) {}
    var p = audio.play();
    if (p && p.catch) {
      p.then(function () { armed = true; label(); })
       .catch(function () { armed = false; label(); });   // blocked, not broken
    }
  }

  /* A gesture anywhere on the page is enough for the browser to allow sound later. */
  function arm() {
    if (armed || !audio) return;
    audio.play().then(function () {
      audio.pause();
      try { audio.currentTime = 0; } catch (e) {}
      armed = true;
      label();
    }).catch(function () {});
  }

  function update(state) {
    if (!state) return;
    var band = state.risk ? state.risk.band : null;
    if (band === 'CRITICAL' && lastBand !== 'CRITICAL') play();
    lastBand = band;

    var events = state.events || [];
    for (var i = events.length - 1; i >= 0; i--) {
      if (events[i].level !== 'critical') continue;
      var id = events[i].t + '|' + events[i].text;
      if (id !== lastCriticalEvent) {
        // Only sound for an entry that arrived after this page loaded. Reconnecting to
        // a running mission must not replay every critical thing that already happened.
        if (lastCriticalEvent !== null) play();
        lastCriticalEvent = id;
      }
      break;
    }
  }

  function toggle() {
    muted = !muted;
    safeSet(MUTE_KEY, muted ? '1' : '0');
    if (!muted) arm();
    label();
  }

  function init() {
    audio = new Audio('audio/alert.mp3');
    audio.preload = 'auto';
    muted = safeGet(MUTE_KEY) === '1';
    button = document.getElementById('alarm');
    if (button) button.addEventListener('click', toggle);
    ['pointerdown', 'keydown'].forEach(function (ev) {
      window.addEventListener(ev, function once() {
        window.removeEventListener(ev, once);
        if (!muted) arm();
      }, { once: true });
    });
    label();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { update: update, toggle: toggle, isMuted: function () { return muted; } };
})();
