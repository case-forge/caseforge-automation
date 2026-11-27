#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

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

export CASEFORGE_RUNTIME_LABEL="${CASEFORGE_RUNTIME_LABEL:-calendar-finder-worker}"
export CASEFORGE_MODEL_LABEL="${CASEFORGE_MODEL_LABEL:-calendar-finder}"

exec python3 tools/load_kv_secrets.py exec -- \
  python3 -m tools.calendar_finder work-loop --allow-write \
  --poll-seconds "${CASEFORGE_CALENDAR_FINDER_WORKER_POLL_SECONDS:-5}" "$@"
