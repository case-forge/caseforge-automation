#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/job-harness.sh"

caseforge_job_init telemetry-backup --no-telemetry-root
caseforge_job_run "telemetry backup" python3 tools/monitoring/telemetry_onedrive_backup.py
