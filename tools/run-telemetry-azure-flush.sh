#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/job-harness.sh"

caseforge_job_init telemetry-azure-flush

caseforge_job_begin "telemetry flush + local retention"
fails=0

printf '[%s] telemetry postgres flush start\n' "$(date -Is)"
python3 tools/telemetry_sqlite.py flush-to-postgres || fails=$((fails + 1))
printf '[%s] telemetry postgres flush complete\n' "$(date -Is)"

printf '[%s] telemetry local retention start\n' "$(date -Is)"
python3 tools/telemetry_sqlite.py maintenance || fails=$((fails + 1))
printf '[%s] telemetry local retention complete\n' "$(date -Is)"

printf '[%s] state_snapshots retention preview start\n' "$(date -Is)"
python3 tools/telemetry_sqlite.py prune-state-snapshots || fails=$((fails + 1))
printf '[%s] state_snapshots retention preview complete\n' "$(date -Is)"

caseforge_job_end "telemetry flush + local retention" "$fails"
