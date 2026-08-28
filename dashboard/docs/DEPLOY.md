# Deploying AFRICA RESQ on a VPS

The command server is one container behind Caddy, which gets and renews the TLS
certificate on its own. A 1 GB VPS is enough; the app is idle-cheap and its working set
is a few hundred survivor and hazard records.

## Before you start

- A VPS with Docker Engine and the Compose plugin.
- A domain with an **A record pointing at the VPS**, resolving *before* you start the
  stack. Caddy asks Let's Encrypt for a certificate on first boot, and that fails if DNS
  has not propagated.
- Ports **80** and **443** reachable. Port 80 is not optional — the ACME challenge uses it.

## Give the server read access first

The repository is **private**, so the server needs its own credential. A deploy key is
the right one: read-only, scoped to this repository alone, and revocable without
touching your account.

On the VPS, as root:

```bash
ssh-keygen -t ed25519 -C "africa-resq deploy key" -f /root/.ssh/resq_deploy -N ""
cat /root/.ssh/resq_deploy.pub
```

Paste that public key at **Settings → Deploy keys → Add deploy key** on
`github.com/nour000304/AFRICA-RESQ`. Leave *Allow write access* unchecked. Then tell
SSH to use it:

```bash
cat >> /root/.ssh/config <<'EOF'
Host github.com
  IdentityFile /root/.ssh/resq_deploy
  IdentitiesOnly yes
EOF
chmod 600 /root/.ssh/config
ssh -T git@github.com          # expect: "successfully authenticated"
```

## Deploy, the short way

```bash
git clone git@github.com:nour000304/AFRICA-RESQ.git /opt/africa-resq
cd /opt/africa-resq
sudo ./scripts/deploy.sh
```

It installs Docker if missing, generates both tokens, opens 22/80/443, warns you if DNS
is not pointing here yet, brings the stack up and prints the two keys. Running it again
is safe — it never overwrites an existing `.env`.

Add `RESQ_DEMO=1` to start the scripted rover alongside it.

Later updates are just:

```bash
cd /opt/africa-resq && git pull && docker compose up -d --build
```

## Deploy, by hand

```bash
git clone git@github.com:nour000304/AFRICA-RESQ.git africa-resq && cd africa-resq

cp .env.example .env
openssl rand -base64 32          # → RESQ_ROVER_TOKEN
openssl rand -base64 32          # → RESQ_OPERATOR_TOKEN
nano .env                        # set the domain, the email, and both tokens

docker compose up -d
docker compose logs -f caddy     # watch the certificate get issued
```

Open `https://your-domain`. The dashboard loads in watching-only mode. Click **Unlock
controls**, paste the operator token, and the mode buttons and the stop control come
alive. The browser keeps it, so this is a once-per-device step.

To run the scripted rover so a hosted instance has something to show:

```bash
docker compose --profile demo up -d
```

## Connecting the real rover

From the Pi, on the same network or over the internet:

```bash
export RESQ_ROVER_TOKEN='<the rover token from .env>'
python -m rover.hardware_client --url wss://your-domain/ws/rover
```

`wss://`, not `ws://` — the token is a bearer secret and plain `ws://` puts it on the
wire in clear text. The client reads `$RESQ_ROVER_TOKEN` by itself; pass `--token` only
if you would rather not put it in the environment.

## The two tokens

| | Grants | If it leaks |
|---|---|---|
| `RESQ_ROVER_TOKEN` | pushing telemetry | someone can invent survivors and hazards on a live rescue board |
| `RESQ_OPERATOR_TOKEN` | commanding the rover | someone can stop, release, or drive the robot |

Watching is deliberately not gated. During an incident, far more people need to see the
board than to drive it, and gating the view is the kind of friction that gets worked
around by sharing the operator key.

Rotate a token by editing `.env` and running `docker compose up -d`. Every rover and
every unlocked dashboard has to present the new one.

## Run one worker, not several

Mission state, the websocket hub and the broadcast loop all live in one process's
memory. A second worker gets its own copy: half the dashboards would see one picture and
half another, and a stop command would reach only the rovers attached to one of them.
The Dockerfile pins `--workers 1` for that reason.

If you ever need more than one instance, the fix is a shared bus (Redis pub/sub for
state, one owner per mission) — not more workers.

## Firewall

```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

The app container is not published to the host — `expose`, not `ports` — so 8000 is
reachable only from Caddy on the internal Docker network. Nothing serves plain HTTP to
the outside.

## Operating it

```bash
docker compose ps                       # health column comes from /api/health
docker compose logs -f resq
docker compose restart resq             # clears mission memory: survivors, hazards, log
docker compose pull && docker compose up -d --build     # deploy a new version
```

There is no database. Restarting the container ends the mission on the board, which is
the honest behaviour for a live incident view — but it does mean **the log is not a
record**. If you need one, capture `/api/state` on a timer:

```bash
watch -n 5 'curl -s https://your-domain/api/state >> mission.jsonl'
```

## Backups

Two things are worth keeping: `.env` and the `caddy_data` volume (the certificates).
Everything else is rebuilt from the repository.

```bash
docker run --rm -v africa-resq_caddy_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/caddy-data.tgz -C /data .
```

## When something is wrong

| Symptom | Cause |
|---|---|
| Certificate never issues | DNS not pointing here yet, or port 80 blocked. Check `docker compose logs caddy`. |
| Dashboard loads, banner says waiting for a rover | No rover connected. `docker compose --profile demo up -d`, or check the rover's token. |
| Rover connects then drops immediately | Token mismatch. The server logs "Rejected a rover connection with a bad token." |
| Controls stay locked after unlocking | Operator token mismatch, or the browser is blocking storage — the key is re-asked every reload. |
| Board freezes but the page is live | Link lost. The dashboard says so and stops presenting the picture as current. |
