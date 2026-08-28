/* Where the survivors go once they are out.
 *
 * Deliberately not a marker on the search grid. That canvas is 24 by 18 metres and every
 * shelter here is kilometres away, so a pin on it would be a lie about scale — and
 * map.js already says out loud that it is a survey grid and not a slippy map. What an
 * incident commander needs from this panel is a direction, a distance and how long it
 * takes, which is three lines of text and an arrow.
 *
 * The list is fetched once, from this server, on the same origin. The anchor does not
 * move during a mission, so neither does the answer, and nothing here reaches the
 * internet: a board on a radio link answers the shelter question with the uplink down,
 * which is exactly when it gets asked.
 */
window.ShelterPanel = (function () {
  var host, tag;

  function fmtKm(km) {
    return km < 1 ? Math.round(km * 1000) + ' m' : km.toFixed(1) + ' km';
  }

  /* Walking is the number that matters when the roads are gone, so it leads. Driving is
     shown beside it, and both are estimates — the panel says so once, in the header. */
  function fmtEta(row) {
    var walk = row.estimated_walk_minutes, drive = row.estimated_drive_minutes;
    return (walk >= 60 ? Math.round(walk / 60) + ' h' : walk + ' min') +
           ' on foot · ' + (drive < 1 ? '<1' : drive) + ' min driving';
  }

  function row(entry) {
    var s = entry.shelter;
    var li = document.createElement('li');

    var top = document.createElement('div');
    top.className = 'sh__top';
    /* The arrow points where the shelter is, in true bearing. Rotation only — no colour,
       because nothing on this panel is a hazard and colour here would read as one. */
    top.innerHTML =
      '<span class="sh__arrow" style="transform:rotate(' + entry.bearing_deg + 'deg)"' +
      ' aria-hidden="true">↑</span>' +
      '<span class="sh__name"></span>' +
      '<span class="sh__dir">' + entry.direction + '</span>' +
      '<span class="sh__km">' + fmtKm(entry.distance_km) + '</span>';
    top.querySelector('.sh__name').textContent = s.name;
    li.appendChild(top);

    var sub = document.createElement('div');
    sub.className = 'sh__sub';
    sub.textContent = s.city + ' · ' + s.type.replace(/_/g, ' ') +
                      ' · holds ~' + s.capacity.toLocaleString();
    li.appendChild(sub);

    var eta = document.createElement('div');
    eta.className = 'sh__eta';
    eta.innerHTML = fmtEta(entry);
    li.appendChild(eta);

    li.title = s.address + (s.contact ? ' — ' + s.contact : '');
    return li;
  }

  function empty(text) {
    host.innerHTML = '';
    var li = document.createElement('li');
    li.className = 'empty';
    li.textContent = text;
    host.appendChild(li);
  }

  function render(body) {
    var found = (body && body.nearest) || [];
    if (!found.length) {
      empty('No shelter is on file for this region.');
      return;
    }
    host.innerHTML = '';
    found.forEach(function (entry) { host.appendChild(row(entry)); });
    tag.textContent = found.length + ' nearest · estimates';
  }

  function load() {
    host = document.getElementById('shelters');
    tag = document.getElementById('shelterTag');
    if (!host) return;

    /* Relative, so it follows the board wherever it is served from — a VPS behind a
       proxy, or a Pi on a field network with no name at all. */
    fetch('api/nearest_shelter?limit=3', { headers: { accept: 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(render)
      .catch(function () {
        /* Say what is missing rather than showing an empty box. A blank panel reads as
           "there is nowhere to go", which is a different and much worse claim. */
        empty('Shelter list unavailable. The command server did not answer.');
        tag.textContent = '';
      });
  }

  return { load: load };
})();
