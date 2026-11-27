#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/job-harness.sh"

caseforge_job_init prospect-queue --no-telemetry-root
caseforge_job_run "prospect queue sweep" python3 tools/mail_intake/prospect_queue.py sweep
