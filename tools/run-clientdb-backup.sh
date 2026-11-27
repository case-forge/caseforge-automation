#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/job-harness.sh"

caseforge_job_init clientdb-backup --no-telemetry-root
caseforge_job_run "clientdb backup" python3 tools/documenso/clientdb_backup.py
