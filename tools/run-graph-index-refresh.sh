#!/usr/bin/env bash

set -euo pipefail
write_job_stamp() { python3 tools/monitoring/job_stamp.py "$@" 2>/dev/null || return 0; }

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="$ROOT_DIR/telemetry/graph-index-refresh.lock"
LOG_FILE="$ROOT_DIR/telemetry/graph-index-refresh.log"
MODE="delta"

mkdir -p "$ROOT_DIR/telemetry"

usage() {
  cat <<'USAGE'
Usage: bash tools/run-graph-index-refresh.sh [--delta|--full|--hot]

  --delta  Consume Graph delta tokens for all configured live roots. Default.
  --full   Rebuild all configured live roots from scratch.
  --hot    Rebuild only recently active top-level matter folders.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --delta)
      MODE="delta"
      ;;
    --full)
      MODE="full"
      ;;
    --hot|--hot-matter-folders)
      MODE="hot"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ -f "$ROOT_DIR/.secrets/caseforge-env" ]]; then
  set -a
  source "$ROOT_DIR/.secrets/caseforge-env"
  set +a
fi

export CASEFORGE_RUNTIME_LABEL="${CASEFORGE_RUNTIME_LABEL:-graph-index-cron}"
export CASEFORGE_MODEL_LABEL="${CASEFORGE_MODEL_LABEL:-none}"

{
  flock -n 9 || {
    printf '[%s] graph index refresh already running; skipped\n' "$(date -Is)"
    exit 0
  }

  cd "$ROOT_DIR"
  printf '[%s] graph index refresh start mode=%s\n' "$(date -Is)" "$MODE"
  HC_SLUG="graph-index-refresh-${MODE}"
  refresh_rc=0
  case "$MODE" in
    delta)
      python3 tools/graph_index.py refresh || refresh_rc=$?
      ;;
    full)
      python3 tools/graph_index.py refresh --full || refresh_rc=$?
      ;;
    hot)
      python3 tools/graph_index.py refresh \
        --hot-matter-folders \
        --hot-hours "${GRAPH_INDEX_HOT_HOURS:-24}" \
        --hot-min-changes "${GRAPH_INDEX_HOT_MIN_CHANGES:-3}" \
        --hot-limit "${GRAPH_INDEX_HOT_LIMIT:-10}" || refresh_rc=$?
      ;;
  esac
  if [[ "$refresh_rc" -ne 0 ]]; then
    printf '[%s] graph index refresh FAILED mode=%s rc=%s\n' "$(date -Is)" "$MODE" "$refresh_rc"
    write_job_stamp "$HC_SLUG" fail "refresh rc=$refresh_rc"
    if [[ -n "${CASEFORGE_HEALTHCHECKS_PING_BASE:-}" ]]; then
      curl -fsS -m 10 --retry 2 -o /dev/null \
        "${CASEFORGE_HEALTHCHECKS_PING_BASE}/${HC_SLUG}/fail?create=1" 2>/dev/null || true
    fi
    exit "$refresh_rc"
  fi
  printf '[%s] graph index refresh complete mode=%s\n' "$(date -Is)" "$MODE"
  case "$MODE" in
    delta) closure_unit="ikenga-matter-folder-closure.service" ;;
    full) closure_unit="ikenga-matter-folder-closure-closed.service" ;;
    *) closure_unit="" ;;
  esac
  if [[ -n "$closure_unit" ]] && command -v systemctl >/dev/null 2>&1; then
    if timeout 600 systemctl start "$closure_unit"; then
      printf '[%s] folder closure scan complete unit=%s\n' "$(date -Is)" "$closure_unit"
    else
      printf '[%s] folder closure scan FAILED unit=%s\n' "$(date -Is)" "$closure_unit"
    fi
  fi
  write_job_stamp "$HC_SLUG" ok
  if [[ -n "${CASEFORGE_HEALTHCHECKS_PING_BASE:-}" ]]; then
    curl -fsS -m 10 --retry 2 -o /dev/null \
      "${CASEFORGE_HEALTHCHECKS_PING_BASE}/${HC_SLUG}?create=1" 2>/dev/null || true
  fi
} 9>"$LOCK_FILE" >>"$LOG_FILE" 2>&1
