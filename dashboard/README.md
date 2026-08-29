# AFRICA RESQ — Rescue Command Dashboard

The command side of the AFRICA RESQ rover: a live dashboard that turns rover telemetry
into a decision. Live feed, survivors, hazards, an explainable risk score, a survey map,
and a recommended next action.

```
rover  ──ws──▶  /ws/rover  ──▶  fusion · risk · priority · pathing  ──▶  /ws/dashboard  ──ws──▶  operator
                    ▲                                                          │
                    └──────────────── e-stop, mode, drive ─────────────────────┘
```

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8000    # command server
.venv/bin/python -m rover.simulator                                       # demo rover
```

Open **http://localhost:8000**. No build step, no npm, no internet — fonts are vendored
locally, so it runs on a Pi in the field with the radio link as its only network.

## What the demo shows

The simulator is a small sensor model, not a list of canned readings: the scene has
ground truth (two people, a fire, a debris pile at fixed coordinates) and every frame is
rendered from the rover's actual pose. Distant people produce small boxes and low
confidence; the gas and heat readings fall off with distance from the fire. The server's
projection, fusion and route planning are genuinely being exercised.

| t | what happens |
|---|---|
| 0 s | rover enters at A1, sweeps east along row 1 |
| 15 s | turns north at D1 and holds to observe |
| 17 s | camera picks up something person-shaped, far off — logged as an unconfirmed contact |
| 22 s | thermal array finishes warming, finds a heat signature in the same place |
| 27 s | fire in D3, directly between the rover and the contact; the gas front arrives |
| 34 s | D3 is now impassable — the planner offers the long way round |
| 40 s | rover takes the safe corridor, east then north |
| 62 s | closes on the survivor; confidence rises as the range falls |
| 70 s | a second, partly buried contact appears to the west, and ranks below the first |

## The five answers on screen

**Is there a survivor, and how sure are we?** Evidence is combined in log-odds
(`server/fusion.py`). Camera and thermal each contribute a likelihood ratio, so agreement
compounds and disagreement subtracts, and every term stays separately reportable — the
chips under each survivor are the actual maths, not a summary of it. A sensor that did
not report contributes exactly zero and is listed as missing evidence.

Two details worth pointing at in a demo:

- **Thermal is discounted in a hot scene.** At 55 °C a human body is no longer the
  hottest thing in frame, so the thermal term is scaled down and the panel says so.
- **A working thermal array that sees nothing is evidence against**, not neutral. A
  camera-only contact does not get promoted to a survivor.

**Where are they?** Not "near the rover" — `server/geometry.py` solves the triangle. Range
comes from the apparent height of the box against a known field of view, bearing from how
far off-centre it sits. The survivor is placed at its own cell and stays there as the
rover moves.

**Is it safe to send people in?** `server/risk.py` scores 0–100 from named causes, each
with its reading, its threshold and its weight. Thresholds are the real ones — 10 % LEL
evacuation, 35 ppm CO exposure limit, 19.5 % oxygen minimum. A sensor that is not reading
becomes an `unknown` cause, and unknown never lowers the score.

**Which way in?** `server/pathing.py` plans twice over the same hazard field — once for
distance, once for risk — and shows both, so the operator sees the trade rather than a
single answer. Cells above the impassable threshold are removed from the graph.

**Who first?** `server/priority.py` ranks survivors on confidence, local danger,
reachability and how recently they were seen, and carries the breakdown so the order can
be argued with.

## The risk ledger

The meter is the explanation. Every cause owns a slice of the column sized by the points
it contributed; the row beside it, aligned to the same height, names the reading and the
limit it crossed. It fills from the bottom, biggest driver first, so the thing to fix is
always at the base. Solid ramp = a hazard. Hatched white = a reason to go in anyway.
Hatched grey = a sensor that is not reading. Nothing on the meter is ever green.

## Connecting real hardware

The rover pushes `RoverFrame` JSON to `ws://<host>:8000/ws/rover` at 2–10 Hz, or POSTs the
same object to `/api/frame`. `server/schemas.py` is the contract; `rover/hardware_client.py`
is a working skeleton for a Pi. Send `frame_jpeg` as a base64 data URI and the feed panel
shows the real camera instead of the drawn scene.

Any sensor you cannot read must be sent as `null`, never as a plausible default. That is
the whole difference between "the air is clear" and "we did not measure the air".

### The camera rover

A trained fire and smoke detector ships in `models/fire_smoke.pt`, so a laptop or a Pi
with a webcam is a working rover with no other hardware:

```bash
pip install -r requirements.txt -r requirements-perception.txt
python -m rover.camera_client --at D3 --heading 90
```

`--at` and `--heading` are where the camera is installed and which way it points, not
readings. It streams real detections, real boxes and the real camera feed, and reports
every sensor it does not have as `null` — so the risk ledger shows the air as unmeasured
rather than clear.

Two models run over each frame: `fire_smoke.pt` for hazards and stock `yolov8n.pt` for
people, whose detections feed the fusion, geometry and priority chain. COCO is trained on
ordinary photographs rather than on casualties in smoke, so its person score is the
weakest evidence on the board — which is why a camera-only contact never reaches the
confirmed band on its own. [docs/PERCEPTION.md](docs/PERCEPTION.md) has the detail.

## Operator controls

| Control | Effect |
|---|---|
| Manual / Assisted / Autonomous | sets the mode and forwards it to the rover |
| Stop rover (or <kbd>Esc</kbd>) | emergency stop, held until released |
| Test detector | runs the rover's two models on the viewer's own camera, in their browser, on their machine — nothing is sent to the server and the mission is untouched. It answers "is the detection real?", which a board showing a simulated rover cannot. |
| Alarm | sounds once when risk reaches critical or a critical entry hits the log — on transitions, never on a loop. Muting is per browser and is never locked, because someone watching read-only still owns their own speakers. |

If frames stop arriving for four seconds the server marks the link lost, logs it, and the
recommendation becomes "restore the radio link before sending anyone in" — the screen
never presents a stale picture as current.

## Where the grid is on Earth

The grid is metres from its south-west corner and stays that way, because a rescue team
calls cells and not coordinates. But "where do we take them" and "route the ambulance"
cannot be asked in metres from a corner, so the two frames meet in one module —
`server/geo.py` — and nothing above or below it has to learn what GPS is.

The anchor is configuration and never a reading. `RESQ_ORIGIN_LAT` and `RESQ_ORIGIN_LON`
are where the corner was surveyed; `RESQ_GRID_BEARING` is the true bearing of the grid's
north edge, so a grid laid out along a street resolves as correctly as one along the
meridian. The defaults put the demo in downtown Cairo.

## Somewhere to send them

Thirty-eight evacuation and gathering points across thirteen Egyptian cities — stadiums,
civic squares, parks and open ground — with capacities, addresses and numbers that answer.
The **Shelter** panel names the three nearest, which way each one is, how far, and how long
on foot.

It is a table of coordinates and the search over it is trigonometry, so it answers with no
network at all. That is the point rather than a footnote: "where do we take them" is the
question that gets asked at the moment the uplink goes, and a board that has to reach a
routing service to answer it has nothing to say at exactly the wrong time.

Walking leads and driving follows, because the case where this panel matters is the one
where the roads are gone. Road routing (`/api/route`) is there too, but only calls out to
a service when `RESQ_OSRM_URL` is set — otherwise it returns a straight-line estimate and
says so, and a straight line is a lower bound on a road, so it says "at least", never
"about".

## The mission record

Every frame and every detection is written to a SQLite store and an append-only JSONL
beside it, so an incident can be reviewed after it ends rather than vanishing with the
process. Query it over HTTP, stream it live, or read the files directly —
[docs/DATA.md](docs/DATA.md).

Writing never touches the event loop: rows go on a queue and one writer task drains it in
a worker thread, because going quiet mid-incident is the one thing the dashboard must not
do. A fire that burns for an hour is one row, not thirty thousand — but a change of
verdict is never collapsed, so the moment a hazard clears is recorded on the instant. A
store that cannot be opened turns recording off and says so; the board still boots.

And the rule the rest of this system is built on holds all the way to disk: a sensor that
did not report is `null` in the record, never `0`.

## Reading it from somewhere else

The dashboard uses `ws://<host>/ws/dashboard`. For anything else there is
`GET /api/state`, plus the four endpoints Didi's backend published for the frontend team
— `/api/status`, `/api/detection`, `/api/risk`, `/api/full` — served here as a projection
of the same live state, so a REST client and the dashboard can never disagree about a
score.

Anything that would rather be pushed than poll can open `GET /api/events/stream`, a
server-sent feed of every recorded row plus that same `/api/full` projection once a
second. Shelters are at `/api/shelters` and `/api/nearest_shelter`, road routes at
`/api/route`, and the record at `/api/events`. [docs/API.md](docs/API.md).

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

184 tests, in under six seconds, no network and no ML dependencies — the box arithmetic in
`rover/perception.py` is exercised against a stub model, because a suite that pulls torch
is a suite nobody runs.

They are written as the claims this README makes: unknown never lowers the risk score, a
working thermal array that sees nothing counts against a survivor, an impassable cell is
not in the route, a survivor is placed at its own cell and not the rover's, and a sensor
that did not report parses to `null` rather than to zero.

## Hosting it

```bash
git clone git@github.com:nour000304/AFRICA-RESQ.git /opt/africa-resq
cd /opt/africa-resq && sudo ./scripts/deploy.sh
```

The script installs Docker if missing, generates both tokens, opens 22/80/443, checks
DNS and starts the stack. The repository is private, so give the server a read-only
deploy key first — [docs/DEPLOY.md](docs/DEPLOY.md) has the three commands.

or by hand:

```bash
cp .env.example .env     # domain, and a token for the rover and one for the operator
docker compose up -d     # add --profile demo to run the scripted rover too
```

One container behind Caddy, which handles TLS on its own. Full steps, token rotation and
the reason this runs a single worker are in [docs/DEPLOY.md](docs/DEPLOY.md).

Deploying on the **visionxart VPS** (as `africa.abdelkbirnainiaa.me`) instead? That uses the org pattern — GHCR, Watchtower
and nginx, not Caddy — and needs a websocket-capable vhost the stock template does not
provide. See [docs/DEPLOY-VISIONXART.md](docs/DEPLOY-VISIONXART.md).

**Two secrets, because the two risks differ.** `RESQ_ROVER_TOKEN` gates telemetry — without
it anyone who finds the host can invent survivors on a live board. `RESQ_OPERATOR_TOKEN`
gates commands — without it anyone can stop, release or drive the robot. Watching is not
gated: during an incident far more people need to see the board than to drive it, and
gating the view just gets the operator key passed around. A dashboard with no token loads
read-only with its controls locked and an **Unlock controls** button in the rail.

Leaving either token empty disables that check, which is fine on a closed network and not
fine on a VPS. The server prints a warning at startup and puts it in the mission log.

## Layout

```
server/     main.py config.py schemas.py fusion.py geometry.py risk.py priority.py
            pathing.py grid.py state.py compat.py
            geo.py shelters.py route.py recorder.py
rover/      simulator.py  hardware_client.py  perception.py  camera_client.py
models/     fire_smoke.pt  yolov8n.pt
dashboard/  index.html  css/  js/  fonts/  audio/
docs/       TELEMETRY.md  PERCEPTION.md  API.md  DATA.md  DEPLOY.md
scripts/    deploy.sh
deploy/     nginx-africa-resq.conf.template
.github/    workflows/deploy.yml
Dockerfile  docker-compose.yml  Caddyfile  .env.example
tests/      contract fusion risk geometry pathing perception compat mission
            geo shelters recorder route http
requirements.txt  requirements-perception.txt  requirements-dev.txt
```


