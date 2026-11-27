#!/usr/bin/env bash
set -euo pipefail

LAB_DIR="${C100_LAB_DIR:-$HOME/c100-lab}"
APP_DIR="$LAB_DIR/c100-application"
URL="http://127.0.0.1:3000"
compose() { (cd "$APP_DIR" && docker compose "$@"); }

up() {
  command -v docker >/dev/null || { echo "docker is needed"; exit 1; }
  mkdir -p "$LAB_DIR"
  [ -d "$APP_DIR/.git" ] || git clone --depth 1 https://github.com/ministryofjustice/c100-application.git "$APP_DIR"
  cd "$APP_DIR"

  sed -i 's/config.force_ssl = true/config.force_ssl = false/; s/config.assume_ssl = true/config.assume_ssl = false/' config/environments/production.rb
  sed -i 's/secure: Rails.env.production?,/secure: false,/' config/initializers/session_store.rb
  sed -i 's/"3000:3000"/"127.0.0.1:3000:3000"/' docker-compose.yml

  cat > docker-compose.override.yml <<'YAML'
services:
  web:
    environment:
      SECRET_KEY_BASE: lab-only-not-a-secret
      EXTERNAL_URL: http://127.0.0.1:3000
      COURT_API_BASE_URL: http://127.0.0.1:9
      COURT_API_CLIENT_ID: lab
      COURT_API_CLIENT_SECRET: lab
      COURT_API_SCOPE: lab
      COURT_API_TOKEN_URL: http://127.0.0.1:9
      GOVUK_NOTIFY_API_KEY: lab-lab-lab-lab-lab-lab-lab-lab-lab-lab-lab-lab-lab-lab-lab
      GOVUK_NOTIFY_BEARER_TOKEN: lab
      HTTP_AUTH_USER: lab
      HTTP_AUTH_PASSWORD: lab
      ORDNANCE_SURVEY_API_KEY: lab
      RAILS_MIN_THREADS: "2"
      SKIP_VIRUS_CHECK: "true"
      QUEUE_ADAPTER: async
      DEV_TOOLS_ENABLED: "true"
    volumes:
      - ./config/environments/production.rb:/usr/src/app/config/environments/production.rb:ro
      - ./config/initializers/session_store.rb:/usr/src/app/config/initializers/session_store.rb:ro
YAML

  compose build web
  compose up -d db cache
  sleep 5
  compose run --rm -e RAILS_ENV=production -e SECRET_KEY_BASE=lab web bundle exec rails db:create db:schema:load
  compose up -d web
  for _ in $(seq 1 45); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "$URL/ping.json" || true)" = 200 ] && { echo "Lab is up: $URL"; return; }
    sleep 4
  done
  echo "The lab did not answer in time; try: docker compose logs web"; exit 1
}

status() {
  if [ "$(curl -s -o /dev/null -w '%{http_code}' "$URL/ping.json" || true)" = 200 ]; then echo "up: $URL"; else echo "down"; fi
}

down() {
  [ -d "$APP_DIR" ] && compose down -v --rmi local --remove-orphans || true
  rm -rf "$LAB_DIR"
  echo "Lab removed."
}

case "${1:-}" in
  up) up ;;
  status) status ;;
  down) down ;;
  *) echo "usage: lab.sh up|status|down"; exit 2 ;;
esac
