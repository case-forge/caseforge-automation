#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="$ROOT_DIR/telemetry/repo-maintenance.lock"
LOG_FILE="$ROOT_DIR/telemetry/repo-maintenance.log"
RETENTION_DAYS=30

usage() {
  cat <<'USAGE'
Usage: bash tools/run-repo-maintenance.sh [--older-than-days N]

Runs non-destructive maintenance checks and writes JSON reports under telemetry/.
Cleanup is preview-only; this wrapper never deletes files.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --older-than-days)
      RETENTION_DAYS="${2:-}"
      if [[ -z "$RETENTION_DAYS" ]]; then
        printf 'Missing value for --older-than-days\n' >&2
        exit 2
      fi
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

mkdir -p "$ROOT_DIR/telemetry"


export CASEFORGE_RUNTIME_LABEL="${CASEFORGE_RUNTIME_LABEL:-repo-maintenance-cron}"
export CASEFORGE_MODEL_LABEL="${CASEFORGE_MODEL_LABEL:-none}"
export CASEFORGE_TELEMETRY_ROOT="${CASEFORGE_TELEMETRY_ROOT:-$ROOT_DIR/telemetry}"

run_report() {
  local label="$1"
  local output="$2"
  shift 2
  local tmp="${output}.tmp"
  printf '[%s] repo maintenance %s start\n' "$(date -Is)" "$label"
  python3 tools/agents/repo_maintenance.py "$@" --json > "$tmp"
  mv "$tmp" "$output"
  printf '[%s] repo maintenance %s complete\n' "$(date -Is)" "$label"
}

{
  flock -n 9 || {
    printf '[%s] repo maintenance already running; skipped\n' "$(date -Is)"
    exit 0
  }

  cd "$ROOT_DIR"
  printf '[%s] repo maintenance suite start\n' "$(date -Is)"
  run_report cleanup "$ROOT_DIR/telemetry/repo-maintenance-cleanup.json" cleanup --older-than-days "$RETENTION_DAYS"
  run_report pii "$ROOT_DIR/telemetry/repo-maintenance-pii.json" pii-scan
  run_report hardcoded-paths "$ROOT_DIR/telemetry/repo-maintenance-hardcoded-paths.json" hardcoded-paths
  run_report missing-script-paths "$ROOT_DIR/telemetry/repo-maintenance-missing-script-paths.json" missing-script-paths
  run_report model-policy-drift "$ROOT_DIR/telemetry/repo-maintenance-model-drift.json" model-policy-drift
  run_report ai-cli-inventory "$ROOT_DIR/telemetry/repo-maintenance-ai-cli-inventory.json" ai-cli-inventory
  run_report doc-discipline "$ROOT_DIR/telemetry/repo-maintenance-discipline.json" doc-discipline
  run_report zero-byte-scan "$ROOT_DIR/telemetry/repo-maintenance-zero-byte.json" zero-byte-scan
  run_report agent-friction "$ROOT_DIR/telemetry/repo-maintenance-agent-friction.json" agent-friction
  printf '[%s] client DB schema audit start\n' "$(date -Is)"
  if python3 tools/sql/clientdb_schema_audit.py --json > "$ROOT_DIR/telemetry/clientdb-schema-audit.json.tmp"; then
    mv "$ROOT_DIR/telemetry/clientdb-schema-audit.json.tmp" "$ROOT_DIR/telemetry/clientdb-schema-audit.json"
    printf '[%s] client DB schema audit complete\n' "$(date -Is)"
  else
    rc=$?
    rm -f "$ROOT_DIR/telemetry/clientdb-schema-audit.json.tmp"
    printf '[%s] WARN client DB schema audit FAILED (exit %s); previous report left in place\n' "$(date -Is)" "$rc"
  fi
  printf '[%s] repo maintenance suite complete\n' "$(date -Is)"
  if [[ -n "${CASEFORGE_HEALTHCHECKS_PING_BASE:-}" ]]; then
    curl -fsS -m 10 --retry 2 -o /dev/null \
      "${CASEFORGE_HEALTHCHECKS_PING_BASE}/repo-maintenance?create=1" 2>/dev/null || true
  fi
} 9>"$LOCK_FILE" >>"$LOG_FILE" 2>&1
