#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="${VE_DEPLOY_CONFIG:-$HERE/deploy.config.json}"
[ -f "$CFG" ] || { echo "missing config: $CFG"; exit 1; }

cfg(){ python3 -c "import json;print(json.load(open('$CFG')).get('$1',''))"; }
APP_NAME=$(cfg app_name);      APP_NAME=${APP_NAME:-voiceexpress}
REPO=$(cfg repo);              BRANCH=$(cfg branch);   BRANCH=${BRANCH:-main}
APP_DIR=$(cfg app_dir);        DATA_DIR=$(cfg data_dir)
SVC_USER=$(cfg service_user);  SVC_USER=${SVC_USER:-$USER}
BIND=$(cfg bind);             BIND=${BIND:-127.0.0.1:8000}
WORKERS=$(cfg workers);        WORKERS=${WORKERS:-2}
TIMEOUT=$(cfg timeout);        TIMEOUT=${TIMEOUT:-120}
ENABLE_PDF=$(cfg enable_pdf);  SCHED=$(cfg maintenance_schedule); SCHED=${SCHED:-Mon 04:00}
SECRET=$(cfg secret_key);      PUBLIC_URL=$(cfg public_url);      DOMAIN=$(cfg domain)
GIT_PUSH=$(cfg git_push)

VENV="$APP_DIR/.venv"; PY="$VENV/bin/python"; PIP="$VENV/bin/pip"; GUNI="$VENV/bin/gunicorn"
ENVF="$DATA_DIR/ve.env"
SUDO=$([ "$(id -u)" -eq 0 ] && echo "" || echo sudo)
say(){ printf '\033[1m[deploy]\033[0m %s\n' "$*"; }

write_env(){
  mkdir -p "$DATA_DIR/uploads" "$DATA_DIR/publications" "$DATA_DIR/media"
  if [ -z "$SECRET" ]; then SECRET=$(python3 -c "import secrets;print(secrets.token_hex(32))"); fi
  cat > "$ENVF" <<EOF
DB_PATH=$DATA_DIR/voice_express.db
UPLOADS_PATH=$DATA_DIR/uploads
PUBLICATIONS_PATH=$DATA_DIR/publications
MEDIA_PATH=$DATA_DIR/media
KEY_FILE=$DATA_DIR/.flask_secret
VE_MAINT_STATE=$DATA_DIR/.ve_maint_state.json
VE_REPO_DIR=$APP_DIR
SECRET_KEY=$SECRET
EOF
  say "wrote $ENVF"
}

install_deps(){
  if command -v apt-get >/dev/null 2>&1; then
    say "apt: python venv/pip, git"
    $SUDO apt-get update -y
    $SUDO apt-get install -y python3 python3-venv python3-pip git
  fi
  [ -d "$VENV" ] || python3 -m venv "$VENV"
  "$PIP" install --upgrade pip >/dev/null
  "$PIP" install -r "$APP_DIR/requirements.txt"
  if [ "$ENABLE_PDF" = "True" ] || [ "$ENABLE_PDF" = "true" ]; then
    say "installing headless Chromium (broadsheet/gazette PDF)"
    $SUDO "$PY" -m playwright install --with-deps chromium || "$PY" -m playwright install chromium
  fi
}

seed_if_empty(){
  if [ ! -f "$DATA_DIR/voice_express.db" ]; then
    local zip; zip=$(ls -1 "$APP_DIR"/ve-seed-*.zip "$APP_DIR"/ve-export-*.zip 2>/dev/null | tail -1 || true)
    if [ -n "$zip" ]; then
      say "seeding DB + media from $(basename "$zip")"
      ( cd "$APP_DIR" && set -a && . "$ENVF" && set +a && "$PY" ve_import.py "$zip" )
    elif [ -f "$APP_DIR/voice_express.db" ]; then
      say "seeding data_dir from the tracked repo DB + media"
      cp "$APP_DIR/voice_express.db" "$DATA_DIR/voice_express.db"
      cp -rn "$APP_DIR/static/uploads/."      "$DATA_DIR/uploads/"      2>/dev/null || true
      cp -rn "$APP_DIR/static/publications/." "$DATA_DIR/publications/" 2>/dev/null || true
      cp -rn "$APP_DIR/static/media/."        "$DATA_DIR/media/"        2>/dev/null || true
    else
      say "no DB and no seed -> starting empty (create content in the admin)"
    fi
  fi
}

install_service(){
  say "installing systemd service: $APP_NAME"
  $SUDO tee "/etc/systemd/system/$APP_NAME.service" >/dev/null <<EOF
[Unit]
Description=The Voice Express ($APP_NAME)
After=network.target

[Service]
User=$SVC_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENVF
ExecStart=$GUNI app:app --workers $WORKERS --timeout $TIMEOUT --bind $BIND
Restart=always

[Install]
WantedBy=multi-user.target
EOF
  local PUSHARG=""; case "$GIT_PUSH" in True|true|1|yes) PUSHARG=" --push";; esac
  $SUDO tee "/etc/systemd/system/$APP_NAME-maint.service" >/dev/null <<EOF
[Unit]
Description=Voice Express maintenance build
[Service]
Type=oneshot
User=$SVC_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENVF
ExecStart=$PY ve_maintenance.py$PUSHARG
EOF
  $SUDO tee "/etc/systemd/system/$APP_NAME-maint.timer" >/dev/null <<EOF
[Unit]
Description=Run Voice Express maintenance on a schedule
[Timer]
OnCalendar=$SCHED
Persistent=true
[Install]
WantedBy=timers.target
EOF
  $SUDO chown -R "$SVC_USER" "$DATA_DIR" "$APP_DIR" || true
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now "$APP_NAME.service"
  $SUDO systemctl enable --now "$APP_NAME-maint.timer"
  say "service up on http://$BIND ; maintenance timer: $SCHED"
}

setup_url(){
  case "$PUBLIC_URL" in
    cloudflare)
      if ! command -v cloudflared >/dev/null 2>&1; then
        say "install cloudflared, then: cloudflared tunnel login && \\"
        say "  cloudflared tunnel create $APP_NAME && cloudflared tunnel route dns $APP_NAME $DOMAIN"
      fi
      say "point the tunnel ingress at http://$BIND  (see HOSTING.md), then: cloudflared service install"
      ;;
    nginx)
      $SUDO tee "/etc/nginx/sites-available/$APP_NAME" >/dev/null <<EOF
server {
  listen 80; server_name $DOMAIN;
  client_max_body_size 80M;
  location / { proxy_pass http://$BIND; proxy_set_header Host \$host; proxy_set_header X-Forwarded-For \$remote_addr; }
}
EOF
      $SUDO ln -sf "/etc/nginx/sites-available/$APP_NAME" "/etc/nginx/sites-enabled/$APP_NAME"
      $SUDO nginx -t && $SUDO systemctl reload nginx
      say "nginx vhost for $DOMAIN -> $BIND ; add TLS with: sudo certbot --nginx -d $DOMAIN"
      ;;
    *) say "public_url: none (serving on $BIND only)";;
  esac
}

cmd_setup(){
  command -v git >/dev/null || { echo "git required"; exit 1; }
  if [ ! -d "$APP_DIR/.git" ]; then
    say "cloning $REPO -> $APP_DIR"; git clone -b "$BRANCH" "$REPO" "$APP_DIR"
  else
    say "repo exists -> pulling"; git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
  fi
  install_deps; write_env; seed_if_empty; install_service; setup_url
  say "done. open your site; admin via the user pill."
}

cmd_update(){
  say "updating $APP_DIR"
  git -C "$APP_DIR" fetch origin "$BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
  "$PIP" install -r "$APP_DIR/requirements.txt"
  $SUDO systemctl restart "$APP_NAME.service"
  say "updated + restarted."
}

cmd_maintenance(){ ( cd "$APP_DIR" && set -a && . "$ENVF" && set +a && "$PY" ve_maintenance.py "${@:-}" ); }
cmd_run(){ ( cd "$APP_DIR" && set -a && . "$ENVF" && set +a && "$GUNI" app:app --workers "$WORKERS" --timeout "$TIMEOUT" --bind "$BIND" ); }
cmd_backup(){
  local out="$DATA_DIR/backups"; mkdir -p "$out"; local ts; ts=$(date +%F_%H%M)
  cp "$DATA_DIR/voice_express.db" "$out/db-$ts.db"
  tar czf "$out/media-$ts.tgz" -C "$DATA_DIR" uploads publications 2>/dev/null || true
  say "backup -> $out/db-$ts.db + media-$ts.tgz"
}
cmd_status(){ $SUDO systemctl status "$APP_NAME.service" --no-pager || true; }
cmd_logs(){ $SUDO journalctl -u "$APP_NAME.service" -f; }

case "${1:-help}" in
  setup) cmd_setup;;
  update) cmd_update;;
  maintenance) shift; cmd_maintenance "$@";;
  backup) cmd_backup;;
  run) cmd_run;;
  status) cmd_status;;
  logs) cmd_logs;;
  *) sed -n '2,20p' "$0";;
esac
