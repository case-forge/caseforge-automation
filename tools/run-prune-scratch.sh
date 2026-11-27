#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/job-harness.sh"

caseforge_job_init prune-scratch
caseforge_job_run "prune-scratch" python3 tools/maintenance/prune_scratch.py --apply
