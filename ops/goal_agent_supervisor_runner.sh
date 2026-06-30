#!/bin/sh
set -u

ROOT="${GOTOUHOU_ROOT:-/root/gotouhou}"
DOCS="$ROOT/docs"
AGENTS="$ROOT/.agents"
RUN_LOCK="$AGENTS/locks/goal-agent-supervisor-run.lock"
ERROR_LOG="$AGENTS/goal-agent-supervisor-last-error.log"
OUTPUT="$AGENTS/goal-agent-supervisor-last-run.json"

mkdir -p "$AGENTS" "$AGENTS/locks"
export HOME="${HOME:-/root}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-/root/.config}"
export GH_CONFIG_DIR="${GH_CONFIG_DIR:-/root/.config/gh}"
export GOCACHE="${GOCACHE:-/root/.cache/go-build}"
export GOPATH="${GOPATH:-/root/go}"
mkdir -p "$GOCACHE" "$GOPATH"

set -- --root "$ROOT"

status=0
if command -v flock >/dev/null 2>&1; then
  if flock -n "$RUN_LOCK" /usr/bin/python3 "$DOCS/ops/goal_agent_manager.py" "$@" > "$OUTPUT" 2> "$ERROR_LOG"; then
    rm -f "$ERROR_LOG"
  else
    status=$?
  fi
else
  if /usr/bin/python3 "$DOCS/ops/goal_agent_manager.py" "$@" > "$OUTPUT" 2> "$ERROR_LOG"; then
    rm -f "$ERROR_LOG"
  else
    status=$?
  fi
fi

if [ "$status" -eq 1 ]; then
  printf '%s\n' 'goal agent supervisor lock is busy; another manager run is active' > "$ERROR_LOG"
  exit 0
fi

exit "$status"
