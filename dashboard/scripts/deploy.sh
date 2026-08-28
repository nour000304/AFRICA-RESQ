#!/usr/bin/env bash
#
# AFRICA RESQ — one-shot VPS bootstrap.
#
#   sudo ./scripts/deploy.sh
#
# The repository is private, so pipe-from-curl will not work: clone it first with a
# deploy key (see docs/DEPLOY.md) and run this from inside the checkout.
#
# Safe to run more than once. It installs Docker only if missing, writes .env only if
# absent, and never overwrites tokens you already have.

set -euo pipefail

REPO_URL="${RESQ_REPO_URL:-}"
APP_DIR="${RESQ_APP_DIR:-/opt/africa-resq}"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }
die()  { printf '\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run as root (sudo $0)"

# ---------------------------------------------------------------- docker
if ! command -v docker >/dev/null 2>&1; then
  bold "Installing Docker Engine…"
  curl -fsSL https://get.docker.com | sh
else
  bold "Docker already installed: $(docker --version)"
fi

docker compose version >/dev/null 2>&1 || die "the Docker Compose plugin is missing"

# ---------------------------------------------------------------- source
if [ -f "./docker-compose.yml" ] && [ -d "./server" ]; then
  APP_DIR="$(pwd)"
  bold "Using the checkout in $APP_DIR"
elif [ -d "$APP_DIR/.git" ]; then
  bold "Updating $APP_DIR…"
  git -C "$APP_DIR" pull --ff-only
else
  [ -n "$REPO_URL" ] || die "set RESQ_REPO_URL=git@github.com:nour000304/AFRICA-RESQ.git and re-run"
  bold "Cloning into $APP_DIR…"
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# ---------------------------------------------------------------- .env
if [ -f .env ]; then
  bold ".env already exists — leaving it alone."
else
  bold "Creating .env"

  domain="${RESQ_DOMAIN:-}"
  while [ -z "$domain" ]; do
    read -rp "  Domain (its A record must already point at this server): " domain
  done

  email="${RESQ_ACME_EMAIL:-}"
  [ -n "$email" ] || read -rp "  Email for Let's Encrypt (blank to skip): " email

  rover_token="$(openssl rand -base64 32 | tr -d '\n')"
  operator_token="$(openssl rand -base64 32 | tr -d '\n')"

  umask 077
  cat > .env <<ENVFILE
RESQ_DOMAIN=$domain
RESQ_ACME_EMAIL=$email
RESQ_ROVER_TOKEN=$rover_token
RESQ_OPERATOR_TOKEN=$operator_token
RESQ_MISSION_ID=${RESQ_MISSION_ID:-RESQ-001}
RESQ_BROADCAST_HZ=${RESQ_BROADCAST_HZ:-8}
ENVFILE
  chmod 600 .env
  bold "Generated both tokens. They are in $APP_DIR/.env and nowhere else — back that file up."
fi

# ---------------------------------------------------------------- firewall
if command -v ufw >/dev/null 2>&1; then
  bold "Opening 22, 80 and 443"
  ufw allow 22/tcp  >/dev/null 2>&1 || true
  ufw allow 80/tcp  >/dev/null 2>&1 || true
  ufw allow 443/tcp >/dev/null 2>&1 || true
  ufw --force enable >/dev/null 2>&1 || true
else
  warn "ufw not installed — open 80 and 443 in your provider's firewall yourself."
fi

# ---------------------------------------------------------------- dns check
domain="$(grep -E '^RESQ_DOMAIN=' .env | cut -d= -f2-)"
if command -v dig >/dev/null 2>&1; then
  resolved="$(dig +short "$domain" A | tail -1)"
  public="$(curl -fsS --max-time 5 https://api.ipify.org || true)"
  if [ -n "$resolved" ] && [ -n "$public" ] && [ "$resolved" != "$public" ]; then
    warn "$domain resolves to $resolved but this host is $public."
    warn "Caddy's certificate request will fail until DNS points here."
  fi
elif [ -z "${RESQ_SKIP_DNS_CHECK:-}" ]; then
  warn "dig not available — skipping the DNS check."
fi

# ---------------------------------------------------------------- up
bold "Building and starting…"
if [ "${RESQ_DEMO:-0}" = "1" ]; then
  docker compose --profile demo up -d --build
else
  docker compose up -d --build
fi

bold "Waiting for the container to report healthy…"
for _ in $(seq 1 30); do
  status="$(docker compose ps --format json resq 2>/dev/null | grep -o '"Health":"[a-z]*"' | head -1 | cut -d'"' -f4 || true)"
  [ "$status" = "healthy" ] && break
  sleep 2
done

echo
bold "AFRICA RESQ is up at https://$domain"
echo
echo "  Operator key (unlocks the controls in the dashboard):"
echo "    $(grep -E '^RESQ_OPERATOR_TOKEN=' .env | cut -d= -f2-)"
echo
echo "  Rover key (for the Pi):"
echo "    $(grep -E '^RESQ_ROVER_TOKEN=' .env | cut -d= -f2-)"
echo
echo "  Watch the certificate get issued:  docker compose logs -f caddy"
echo "  Run the scripted rover:            docker compose --profile demo up -d"
echo "  Stop everything:                   docker compose down"
