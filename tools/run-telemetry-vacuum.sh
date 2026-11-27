#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/job-harness.sh"

caseforge_job_init telemetry-vacuum

caseforge_job_begin "telemetry database vacuum"

printf '[%s] telemetry vacuum start\n' "$(date -Is)"
fails=0
python3 tools/telemetry_sqlite.py vacuum --apply || fails=1
printf '[%s] telemetry vacuum complete\n' "$(date -Is)"

caseforge_job_end "telemetry database vacuum" "$fails"
