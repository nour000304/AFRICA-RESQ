# Deploying on the visionxart VPS, under africa.abdelkbirnainiaa.me

> **This is not how the site currently runs.** The live deployment builds on the server
> from a git clone; see [What is actually deployed](#what-is-actually-deployed) below.
> The GHCR + Watchtower path described in the rest of this file is kept because it is
> the org pattern and the CI workflow still publishes the image, but nothing on the VPS
> pulls it today. Step 1 in particular is *not* a prerequisite any more.

## What is actually deployed

Building on the VPS drops two moving parts: the GHCR package never has to be made
readable, and Watchtower never has to be trusted to notice a digest change. The cost is
a ~40 s build on each deploy, which for a project this size is cheaper than the
machinery it replaces.

```
you: git push                                    (nothing happens on the VPS)
you: ssh visionxart 'cd /opt/clients/africa-resq && git pull && docker compose up -d --build'
```

That second line is the whole update loop. `--build` is what makes the pull take effect;
without it Compose reuses the existing image and the deploy silently does nothing.

| | |
|---|---|
| Path on the VPS | `/opt/clients/africa-resq` |
| Host port | `127.0.0.1:3008` |
| Clone credential | read-only deploy key, `/root/.ssh/resq_deploy` |
| TLS | certbot on the host nginx, auto-renewing |
| Demo rover | `docker compose --profile demo up -d` |

Two files live on the server only, untracked, so `git pull` never touches them:

- `.env` — the domain and both tokens
- `docker-compose.override.yml` — publishes 3008, and disables the bundled Caddy,
  because on this host nginx owns 80/443. It also sets
  `com.centurylinklabs.watchtower.enable=false`: the image is local and has no registry
  to be compared against, so Watchtower would retry a doomed pull every two minutes.

The nginx vhost is the websocket-aware one from `deploy/nginx-africa-resq.conf.template`,
installed at step 3 below — that step is still exactly right, and this app does not work
without it.

---

The rest of this file describes the image-pull path, for the day it is wanted back.

This follows the org pattern from `~/Work/vixart/CLAUDE.md` — the same VPS, nginx and
Watchtower — with two deliberate departures, because this is a personal project rather
than a client site:

- the repository is **`AbdelkbirNA/africa-resq`**, so the image is
  `ghcr.io/abdelkbirna/africa-resq`, not `ghcr.io/visionxartorg/…`
- the hostname is **`africa.abdelkbirnainiaa.me`**, not a `visionxart.com` subdomain

Both mean `scripts/add-vps-site.sh` cannot be used unmodified: it hardcodes the image
owner. The steps below do what it does, by hand, for this project.

```
push to main → GitHub Actions builds → ghcr.io/abdelkbirna/africa-resq:latest
             → Watchtower on the VPS recreates the container within ~2 min
             → nginx africa.abdelkbirnainiaa.me → 127.0.0.1:<port>
```

## 1. Make the GHCR package readable by the VPS

The repository is private, so its container image is private too, and Watchtower cannot
pull it without credentials. Pick one:

- **Make the package public** (repository stays private). After the first successful
  build, open `github.com/users/AbdelkbirNA/packages/container/africa-resq/settings` and
  set visibility to public. Nothing about the source is exposed — a container image is
  the built artefact, and this one holds no secrets: both tokens come from the VPS `.env`
  at runtime.
- **Or log the VPS in.** Create a PAT with `read:packages` only, then
  `ssh visionxart "echo <PAT> | docker login ghcr.io -u AbdelkbirNA --password-stdin"`.

The first is fewer moving parts and nothing on the VPS expires.

## 2. Provision the site directory

`add-vps-site.sh` hardcodes `ghcr.io/visionxartorg/<name>`, so this is the same work done
by hand, with the image owner corrected. It picks the next free host port the same way.

```bash
ssh visionxart 'bash -s' <<"REMOTE"
set -e
DIR=/opt/clients/africa-resq
if [ ! -f "$DIR/docker-compose.yml" ]; then
  LAST=$(grep -rho "127\.0\.0\.1:[0-9]*" /opt/clients/*/docker-compose.yml 2>/dev/null | cut -d: -f2 | sort -n | tail -1)
  PORT=$(( ${LAST:-3000} + 1 ))
  mkdir -p "$DIR"
  cat > "$DIR/docker-compose.yml" <<YML
services:
  app:
    image: ghcr.io/abdelkbirna/africa-resq:latest
    container_name: africa-resq
    restart: unless-stopped
    env_file: .env
    ports:
      - "127.0.0.1:$PORT:8000"
    volumes:
      - africa-resq-data:/data
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }

volumes:
  africa-resq-data:
YML
fi
grep -o "127\.0\.0\.1:[0-9]*" "$DIR/docker-compose.yml" | cut -d: -f2
REMOTE
```

It prints the host port. The nginx step needs it.

## 3. Install the vhost — this app will not work without it

The stock vhost `add-vps-site.sh` writes has no websocket upgrade. This application *is*
websockets: the rover pushes telemetry over one, every dashboard reads state over
another. With the stock vhost the page loads, sits on "waiting for a rover" forever, and
nothing ever appears.

```bash
sed -e "s/__DOMAIN__/africa.abdelkbirnainiaa.me/" -e "s/__PORT__/<port from step 2>/" \
    deploy/nginx-africa-resq.conf.template | \
    ssh visionxart "cat > /etc/nginx/sites-available/africa.abdelkbirnainiaa.me"
ssh visionxart "nginx -t && systemctl reload nginx"
```

It also raises the proxy read timeout to an hour. The nginx default is 60 seconds, which
would cut a live mission board.

## 4. Set the two tokens — before DNS lands, not after

The generated `/opt/clients/africa-resq/.env` only contains `SECRET_KEY`. This app needs
its own two secrets, and the moment the subdomain resolves the dashboard is publicly
reachable.

```bash
ssh visionxart 'cd /opt/clients/africa-resq && \
  printf "RESQ_ROVER_TOKEN=%s\nRESQ_OPERATOR_TOKEN=%s\n" \
    "$(openssl rand -base64 32)" "$(openssl rand -base64 32)" >> .env && \
  chmod 600 .env && grep RESQ_ .env'
```

Copy both values somewhere safe — that file is the only place they exist. The operator
token unlocks the controls in the dashboard; the rover token goes to the Pi.

**If you skip this, the app does not become an open robot control.** With no token
configured it refuses commands and telemetry from any public address and accepts them
only from loopback or a private network. But that also means the real rover cannot
connect over the internet until the tokens are set, so do this step.

## 5. DNS

`abdelkbirnainiaa.me` is registered at Namecheap (`dns1/dns2.registrar-servers.com`) and
its apex points at Vercel. Adding a subdomain does not disturb that — add one record in
the Namecheap advanced DNS panel:

```
Type: A Record    Host: africa    Value: 187.127.230.169    TTL: Automatic
```

There is no API access from here, so this step is by hand.

Then, once it resolves:

```bash
ssh visionxart "certbot --nginx -d africa.abdelkbirnainiaa.me --redirect \
  --non-interactive --agree-tos --keep-until-expiring -m nainiaa.abdelkbir@gmail.com"
```

Certbot edits the vhost in place and keeps the websocket directives.

## 6. Ship it

```bash
git push origin main
gh run watch --repo AbdelkbirNA/africa-resq --exit-status
curl -sI https://africa.abdelkbirnainiaa.me/
```

A red **Deploy to VPS** step on its own does not mean the deploy failed — Hostinger's
edge drops GitHub-runner traffic, and Watchtower picks the new image up within about two
minutes.

## 7. Prove the websockets actually work

The health endpoint answering is not proof; it is HTTP. Check a real socket:

```bash
curl -s https://africa.abdelkbirnainiaa.me/api/health
ssh visionxart "docker logs --tail 20 africa-resq"
```

Then open the dashboard. If it shows the mission clock ticking and the log filling, the
socket is up. If it sits on "waiting for a rover" with an empty log, step 2 did not take.

## Running the demo rover on the VPS

There is no hardware attached, so a hosted instance shows an empty board unless the
scripted rover runs alongside it:

```bash
ssh visionxart 'cd /opt/clients/africa-resq && \
  docker run -d --name africa-resq-sim --restart unless-stopped \
    --network container:africa-resq \
    ghcr.io/abdelkbirna/africa-resq:latest \
    python -m rover.simulator --url ws://127.0.0.1:8000/ws/rover --token "<rover token>"'
```

Sharing the app container's network namespace keeps the simulator on loopback, so it
never crosses nginx and never touches the public interface.

## Watchtower

Watchtower on the VPS polls GHCR every two minutes and recreates any container whose
`:latest` digest changed, which is what actually lands a deploy — GitHub runners cannot
reach this VPS. It only sees the new image if the package is readable (step 1).

## Ports in use

3000 vixart-landing · 3004 dozzle · 3005 volora · 3006 brrani · 3007 btsp-ecole-badar.
Step 2 takes the next free one.
