#!/bin/sh
set -u

ROOT="${GOTOUHOU_ROOT:-/root/gotouhou}"
DOCS="$ROOT/docs"
AGENTS="$ROOT/.agents"
SUMMARY="$AGENTS/last-watchdog-summary.json"
ERROR_LOG="$AGENTS/watchdog-last-error.log"
REGRESSION_LOG="$AGENTS/regression-last-run.log"

mkdir -p "$AGENTS"
export HOME="${HOME:-/root}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-/root/.config}"
export GOCACHE="${GOCACHE:-/root/.cache/go-build}"
export GOPATH="${GOPATH:-/root/go}"
mkdir -p "$GOCACHE" "$GOPATH"

/usr/bin/python3 "$DOCS/ops/run_regression_checks.py" --root "$ROOT" > "$REGRESSION_LOG" 2>&1 || true

if /usr/bin/python3 "$DOCS/ops/agent_watchdog.py" --root "$ROOT" --approve-prs > "$AGENTS/watchdog-last-run.json" 2> "$ERROR_LOG"; then
  rm -f "$ERROR_LOG"
else
  status=$?
  /usr/bin/python3 - "$SUMMARY" "$ERROR_LOG" "$status" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
error_path = Path(sys.argv[2])
status = int(sys.argv[3])
now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
error = error_path.read_text(encoding="utf-8", errors="replace")[-4000:] if error_path.exists() else ""
payload = {
    "version": 1,
    "generated_at": now,
    "root": "/root/gotouhou",
    "watchdog_failed": True,
    "resampled_after_actions": False,
    "failures": [{"type": "watchdog-run-failed", "status": status, "error": error}],
    "actions": [],
    "action_count": 0,
    "started_count": 0,
    "reports": {},
    "repos": {},
    "scopes": {},
    "manager": {"mode": "unknown", "stale": "unknown", "age_seconds": "unknown"},
    "summary_path": str(summary_path),
}
summary_path.parent.mkdir(parents=True, exist_ok=True)
summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
PY
fi

exec /usr/bin/python3 "$DOCS/ops/hourly_progress_mail.py" --brief --watchdog-summary "$SUMMARY"
