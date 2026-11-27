#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$ROOT_DIR/tools/caseforge-logrotate.conf"
RENDERED="$(mktemp)"
trap 'rm -f "$RENDERED"' EXIT

sed "s#/home/caseforge/caseforge-automation#${ROOT_DIR}#g" "$TEMPLATE" >"$RENDERED"

if [ -w /etc/logrotate.d ] 2>/dev/null || [ "$(id -u)" = "0" ]; then
    cp "$RENDERED" /etc/logrotate.d/caseforge-automation
    chmod 644 /etc/logrotate.d/caseforge-automation
    echo "Installed /etc/logrotate.d/caseforge-automation for $ROOT_DIR"
else
    cp "$RENDERED" "$ROOT_DIR/tmp/caseforge-logrotate.rendered.conf"
    echo "No root: rendered config at tmp/caseforge-logrotate.rendered.conf"
    echo "Run:  logrotate --state ~/.caseforge-logrotate.state $ROOT_DIR/tmp/caseforge-logrotate.rendered.conf"
fi
