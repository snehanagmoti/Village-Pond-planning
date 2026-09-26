#!/bin/sh
# Run after SSH login on allotted system 2; no credentials are stored here.
set -eu
export PYTHONPATH="$HOME/.local/share/pond-service/packages"
PY="$HOME/village-pond-api/.venv/bin/python"
CFG="$HOME/.local/share/pond-service/supervisord.conf"
if "$PY" -m supervisor.supervisorctl -c "$CFG" pid >/dev/null 2>&1; then
  STATUS=$("$PY" -m supervisor.supervisorctl -c "$CFG" status pond-web || true)
  case "$STATUS" in
    *RUNNING*) : ;;
    *) "$PY" -m supervisor.supervisorctl -c "$CFG" start pond-web ;;
  esac
else
  "$PY" -m supervisor.supervisord -c "$CFG"
fi
sleep 4
"$PY" -m supervisor.supervisorctl -c "$CFG" status
curl --fail --max-time 10 http://127.0.0.1:3000/health/ready
