#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -f "${CASEFORGE_LUKS_PATHS_FILE:-/etc/caseforge-automation/luks-paths.env}" ]]; then
  set -a
  source "${CASEFORGE_LUKS_PATHS_FILE:-/etc/caseforge-automation/luks-paths.env}"
  set +a
fi

if [[ -f "${CASEFORGE_FLAGS_FILE:-/etc/caseforge-automation/flags.env}" ]]; then
  set -a
  source "${CASEFORGE_FLAGS_FILE:-/etc/caseforge-automation/flags.env}"
  set +a
fi

if [[ -f .secrets/azure-sp-env ]]; then
  set -a
  source .secrets/azure-sp-env
  set +a
fi

export CASEFORGE_RUNTIME_LABEL="${CASEFORGE_RUNTIME_LABEL:-calendar-finder-cron}"
export CASEFORGE_MODEL_LABEL="${CASEFORGE_MODEL_LABEL:-calendar-finder}"


LOG_FILE="$REPO_ROOT/telemetry/calendar-finder.log"
LOG_MAX_BYTES="${CASEFORGE_WRAPPER_LOG_MAX_BYTES:-5242880}"
mkdir -p "$(dirname "$LOG_FILE")"
if [[ -f "$LOG_FILE" ]] && (( $(wc -c <"$LOG_FILE") > LOG_MAX_BYTES )); then
  mv -f "$LOG_FILE" "$LOG_FILE.1"
fi
printf '[%s] calendar-finder start args=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2> >(tee -a "$LOG_FILE" >&2)

rc=0
python3 tools/load_kv_secrets.py exec -- bash -c '
  python3 -m tools.calendar_finder poll "$@"; rc=$?
  if [[ -n "${CASEFORGE_HEALTHCHECKS_PING_BASE:-}" ]]; then
    suffix=""; [[ $rc -ne 0 ]] && suffix="/fail"
    curl -fsS -m 10 --retry 2 -o /dev/null "${CASEFORGE_HEALTHCHECKS_PING_BASE}/calendar-finder${suffix}?create=1" 2>/dev/null || true
  fi
  exit $rc' _ "$@" || rc=$?
printf '[%s] calendar-finder exit rc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$rc" >&2
exit "$rc"
