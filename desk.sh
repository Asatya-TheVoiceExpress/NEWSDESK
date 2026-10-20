#!/usr/bin/env bash
# Start, stop or check every Voice Express desk app.
#   ./desk.sh start | stop | restart | status
# Logs go to logs/<app>.log, process ids to logs/<app>.pid.
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")"
export PATH="$HOME/.local/bin:$PATH" PYTHONUNBUFFERED=1
mkdir -p logs

# name port command
APPS=(
  "site 5000 gunicorn -b 127.0.0.1:5000 -w 1 --threads 8 --timeout 120 app:app"
  "desk-editor 8787 python3 desk_editor/serve.py"
  "social 8788 python3 social_manager/serve.py"
  "columnroom 8789 python3 columnroom/serve.py"
  "newsroom 8790 python3 newsroom/serve.py"
  "dtp 8797 python3 dtp.py"
)

up(){ ss -ltn "sport = :$1" 2>/dev/null | grep -q LISTEN; }

start(){
  for a in "${APPS[@]}"; do
    read -r name port cmd <<<"$a"
    if up "$port"; then echo "  $name already on :$port"; continue; fi
    nohup $cmd >>"logs/$name.log" 2>&1 &
    echo $! >"logs/$name.pid"
  done
  sleep 3; status
}

stop(){
  for a in "${APPS[@]}"; do
    read -r name port _ <<<"$a"
    [ -f "logs/$name.pid" ] && kill "$(cat "logs/$name.pid")" 2>/dev/null
    rm -f "logs/$name.pid"
  done
  sleep 1; status
}

status(){
  for a in "${APPS[@]}"; do
    read -r name port _ <<<"$a"
    if up "$port"; then printf '  up    %-12s http://localhost:%s\n' "$name" "$port"
    else printf '  DOWN  %-12s see logs/%s.log\n' "$name" "$name"; fi
  done
}

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  *) echo "usage: $0 start|stop|restart|status"; exit 1 ;;
esac
