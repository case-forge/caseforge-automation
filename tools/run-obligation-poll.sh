#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "${CASEFORGE_LUKS_PATHS_FILE:-/etc/caseforge-automation/luks-paths.env}" ]]; then
  set -a
  source "${CASEFORGE_LUKS_PATHS_FILE:-/etc/caseforge-automation/luks-paths.env}"
  set +a
fi

if [[ -f "$ROOT_DIR/.secrets/caseforge-env" ]]; then
  set -a
  source "$ROOT_DIR/.secrets/caseforge-env"
  set +a
fi

export CASEFORGE_RUNTIME_LABEL="${CASEFORGE_RUNTIME_LABEL:-obligation-poll-cron}"
export CASEFORGE_MODEL_LABEL="${CASEFORGE_MODEL_LABEL:-none}"
export CASEFORGE_TELEMETRY_ROOT="${CASEFORGE_TELEMETRY_ROOT:-$ROOT_DIR/telemetry}"

cd "$ROOT_DIR"

LOG_FILE="$ROOT_DIR/telemetry/obligation-poll.log"
LOG_MAX_BYTES="${CASEFORGE_WRAPPER_LOG_MAX_BYTES:-5242880}"
mkdir -p "$(dirname "$LOG_FILE")"
if [[ -f "$LOG_FILE" ]] && (( $(wc -c <"$LOG_FILE") > LOG_MAX_BYTES )); then
  mv -f "$LOG_FILE" "$LOG_FILE.1"
fi
printf '[%s] obligation-poll start\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2> >(tee -a "$LOG_FILE" >&2)

rc=0
python3 -m products.ikoro.obligation_poll || rc=$?
printf '[%s] obligation-poll exit rc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$rc" >&2
exit "$rc"
