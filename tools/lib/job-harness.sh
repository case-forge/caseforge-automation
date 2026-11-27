#!/usr/bin/env bash

caseforge_job_init() {
  CASEFORGE_JOB_SLUG="$1"
  shift

  CASEFORGE_JOB_ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[1]}")/.." && pwd)"
  local runtime_label="${CASEFORGE_JOB_SLUG}-cron" model_label="none" telemetry_root=1
  local log_slug="$CASEFORGE_JOB_SLUG"
  CASEFORGE_JOB_TIMEOUT_SECONDS=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --runtime-label)       runtime_label="$2"; shift 2 ;;
      --model-label)         model_label="$2"; shift 2 ;;
      --log-slug)            log_slug="$2"; shift 2 ;;
      --no-telemetry-root)   telemetry_root=0; shift ;;
      --timeout)             CASEFORGE_JOB_TIMEOUT_SECONDS="$2"; shift 2 ;;
      *) printf 'caseforge_job_init: unknown option %s\n' "$1" >&2; return 2 ;;
    esac
  done

  export CASEFORGE_JOB_LOCK_FILE
  CASEFORGE_JOB_LOCK_FILE="$CASEFORGE_JOB_ROOT_DIR/telemetry/${log_slug}.lock"
  CASEFORGE_JOB_LOG_FILE="$CASEFORGE_JOB_ROOT_DIR/telemetry/${log_slug}.log"
  mkdir -p "$(dirname "$CASEFORGE_JOB_LOG_FILE")"

  if [[ -f "${CASEFORGE_FLAGS_FILE:-/etc/caseforge-automation/flags.env}" ]]; then
    set -a
    source "${CASEFORGE_FLAGS_FILE:-/etc/caseforge-automation/flags.env}"
    set +a
  fi

  if [[ -f "${CASEFORGE_LUKS_PATHS_FILE:-/etc/caseforge-automation/luks-paths.env}" ]]; then
    set -a
    source "${CASEFORGE_LUKS_PATHS_FILE:-/etc/caseforge-automation/luks-paths.env}"
    set +a
  fi

  if [[ -f "$CASEFORGE_JOB_ROOT_DIR/.secrets/caseforge-env" ]]; then
    set -a
    source "$CASEFORGE_JOB_ROOT_DIR/.secrets/caseforge-env"
    set +a
  fi

  export CASEFORGE_RUNTIME_LABEL="${CASEFORGE_RUNTIME_LABEL:-$runtime_label}"
  export CASEFORGE_MODEL_LABEL="${CASEFORGE_MODEL_LABEL:-$model_label}"
  [[ "$telemetry_root" -eq 1 ]] && \
    export CASEFORGE_TELEMETRY_ROOT="${CASEFORGE_TELEMETRY_ROOT:-$CASEFORGE_JOB_ROOT_DIR/telemetry}"

  return 0
}

job_stamp_write() {
  [[ "${CASEFORGE_JOB_SLUG:-}" =~ ^[a-z0-9][a-z0-9._-]*$ ]] || return 0
  local dir="${CASEFORGE_TELEMETRY_ROOT:-${CASEFORGE_JOB_ROOT_DIR:-.}/telemetry}/job-stamps"
  mkdir -p "$dir" 2>/dev/null || return 0
  local file="$dir/${CASEFORGE_JOB_SLUG}.$1"
  date -u +%Y-%m-%dT%H:%M:%SZ >"$file.tmp$$" 2>/dev/null && mv -f "$file.tmp$$" "$file" 2>/dev/null
  return 0
}

caseforge_job_hc_ping() {
  local suffix=""
  case "${1:-}" in
    fail)  suffix="/fail" ;;
    start) suffix="/start" ;;
  esac
  case "${1:-}" in
    start) ;;
    fail)  job_stamp_write fail ;;
    *)     job_stamp_write ok ;;
  esac
  [[ -z "${CASEFORGE_HEALTHCHECKS_PING_BASE:-}" ]] && return 0
  curl -fsS -m 10 --retry 2 -o /dev/null \
    "${CASEFORGE_HEALTHCHECKS_PING_BASE}/${CASEFORGE_JOB_SLUG}${suffix}?create=1" 2>/dev/null || true
  return 0
}

caseforge_job_run() {
  local display="$1"
  shift
  (
    flock -n 9 || {
      printf '[%s] %s already running; skipped\n' "$(date -Is)" "$display"
      exit 0
    }
    cd "$CASEFORGE_JOB_ROOT_DIR"
    caseforge_job_hc_ping start
    printf '[%s] %s start\n' "$(date -Is)" "$display"
    local rc=0
    if [[ -n "$CASEFORGE_JOB_TIMEOUT_SECONDS" ]]; then
      timeout --signal=TERM --kill-after=30 "$CASEFORGE_JOB_TIMEOUT_SECONDS" "$@" || rc=$?
    else
      "$@" || rc=$?
    fi
    if [[ "$rc" -eq 0 ]]; then
      printf '[%s] %s complete\n' "$(date -Is)" "$display"
      caseforge_job_hc_ping
    elif [[ "$rc" -eq 124 ]]; then
      printf '[%s] %s TIMED OUT after %ss, killed\n' "$(date -Is)" "$display" "$CASEFORGE_JOB_TIMEOUT_SECONDS"
      caseforge_job_hc_ping fail
      exit "$rc"
    else
      printf '[%s] %s failed rc=%s\n' "$(date -Is)" "$display" "$rc"
      caseforge_job_hc_ping fail
      exit "$rc"
    fi
  ) 9>"$CASEFORGE_JOB_LOCK_FILE" >>"$CASEFORGE_JOB_LOG_FILE" 2>&1
}

caseforge_job_begin() {
  exec 9>"$CASEFORGE_JOB_LOCK_FILE"
  flock -n 9 || {
    printf '[%s] %s already running; skipped\n' "$(date -Is)" "$1" >>"$CASEFORGE_JOB_LOG_FILE"
    exit 0
  }
  exec >>"$CASEFORGE_JOB_LOG_FILE" 2>&1
  cd "$CASEFORGE_JOB_ROOT_DIR"
  caseforge_job_hc_ping start
  printf '[%s] %s start\n' "$(date -Is)" "$1"
}

caseforge_job_end() {
  if [[ "${2:-0}" -gt 0 ]]; then
    printf '[%s] %s finished with %s failed step(s)\n' "$(date -Is)" "$1" "$2"
    caseforge_job_hc_ping fail
    return 0
  fi
  printf '[%s] %s complete\n' "$(date -Is)" "$1"
  caseforge_job_hc_ping
}

caseforge_with_shared_lock() {
  local name="$1" wait_seconds="$2"
  shift 2
  local lock_file
  lock_file="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/telemetry/${name}.lock"
  mkdir -p "$(dirname "$lock_file")"
  (
    if ! flock -n 8; then
      printf '[%s] waiting up to %ss for shared lock %s\n' \
        "$(date -Is)" "$wait_seconds" "$name"
      if ! flock -w "$wait_seconds" 8; then
        printf '[%s] TIMED OUT after %ss waiting for shared lock %s; not run\n' \
          "$(date -Is)" "$wait_seconds" "$name"
        exit 75
      fi
      printf '[%s] acquired shared lock %s\n' "$(date -Is)" "$name"
    fi
    "$@" 8>&-
  ) 8>"$lock_file"
}
