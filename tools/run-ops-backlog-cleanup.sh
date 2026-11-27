#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/job-harness.sh"

caseforge_job_init ops-backlog-cleanup --no-telemetry-root
caseforge_job_run "ops backlog cleanup" python3 tools/monitoring/ops_backlog_cleanup.py --apply
