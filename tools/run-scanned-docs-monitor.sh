#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/job-harness.sh"

caseforge_job_init scanned-docs-monitor --runtime-label scanned-docs-cron --no-telemetry-root
caseforge_job_run "scanned docs monitor" python3 tools/scanned_docs/scanned_docs_monitor.py "$@"
