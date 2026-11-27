#!/usr/bin/env bash
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a ANSIBLE_NOCOLOR=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
CRM_DIR="${CRM_DIR:-products/caseforge-crm}"
FAILED=0
step() { printf '\n=== %s\n' "$*"; }
ok() { printf '   ok: %s\n' "$*"; }
bad() { printf '   FAIL: %s\n' "$*"; FAILED=1; }
as_root() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi; }

PREFIX="$(grep -oE '[A-Z]+_CHAT_API_TOKEN' tools/vergil/api.py | head -1 | sed 's/_CHAT_API_TOKEN//')"
[ -n "$PREFIX" ] || { echo "cannot read the environment prefix from tools/vergil/api.py"; exit 2; }
var() { printf '%s_%s' "$PREFIX" "$1"; }

step "1. Provision with Ansible (packages and Node, this machine only)"
if [ "${SKIP_ANSIBLE:-0}" = "1" ]; then
  as_root apt-get update -qq && as_root apt-get install -y -qq python3-venv python3-pip pandoc poppler-utils git curl >/dev/null && ok "packages by apt (Ansible skipped)"
  command -v node >/dev/null || { curl -fsSL https://deb.nodesource.com/setup_24.x | as_root bash - >/dev/null 2>&1; as_root apt-get install -y -qq nodejs >/dev/null; }
else
  as_root apt-get update -qq && as_root apt-get install -y -qq python3-venv python3-pip git curl >/dev/null
  python3 -m venv /tmp/ansible-venv &&
  /tmp/ansible-venv/bin/pip install -q ansible >/dev/null
  INV="$(mktemp)"
  printf '[example]\nlocalhost ansible_connection=local ansible_user=%s\n[linux_ssh_targets]\nlocalhost\n' "$(id -un)" >"$INV"
  echo "   ansible $(/tmp/ansible-venv/bin/ansible --version | head -1)"
  timeout 600 /tmp/ansible-venv/bin/ansible-playbook -i "$INV" deploy/ansible/site.yml --tags system-packages,node \
    -e "checkout_owner_home=$HOME" -e "dev_tooling_enabled=false" 2>&1 </dev/null | tee /tmp/ansible.log | grep -E "^(TASK|PLAY RECAP|fatal|.*failed=)" | tail -40
  if [ "${PIPESTATUS[0]}" -eq 0 ]; then ok "playbook finished"; else bad "playbook failed or timed out (last lines below)"; tail -25 /tmp/ansible.log; fi
fi
command -v node >/dev/null && ok "node $(node -v)" || bad "node is not installed"
command -v pandoc >/dev/null && ok "pandoc present" || bad "pandoc is not installed"

step "2. Python side and the example firm"
python3 -m venv .venv && . .venv/bin/activate
pip install -q -r requirements.txt && ok "requirements installed" || bad "pip install failed"
python -m spacy download en_core_web_sm >/tmp/spacy.log 2>&1 && ok "language model" || { bad "language model download failed"; tail -8 /tmp/spacy.log; }
cp -n profile/firm.example.yaml profile/firm.yaml
python - <<'PY' && ok "profile loads" || bad "profile does not load"
import sys; sys.path.insert(0, "tools")
import firm_profile
print("  firm:", firm_profile.load_base_profile().firm_name)
PY

step "3. Demo (the CRM on built-in sample data, with the training game)"
( cd "$CRM_DIR" && npm ci --ignore-scripts --no-audit --no-fund >/tmp/npm.log 2>&1 ) && ok "CRM packages installed" || { bad "npm ci failed"; tail -15 /tmp/npm.log; }
( cd "$CRM_DIR" && exec node scripts/demo.mjs --port 13000 --game-port 18791 >/tmp/demo.log 2>&1 ) &
DEMO_PID=$!
code=000
for _ in $(seq 1 150); do
  code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:13000/ || true)"
  [ "$code" = "200" ] && break
  kill -0 "$DEMO_PID" 2>/dev/null || break
  sleep 2
done
[ "$code" = "200" ] && ok "the demo builds and its front page answers 200" || { bad "the demo front page answered $code"; tail -20 /tmp/demo.log; }
for path in /settings /api/me/role /training/ /training/api/version; do
  c="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:13000$path" || true)"
  [ "$c" = "200" ] && ok "$path answers 200" || { bad "$path answered $c"; SHOW_DEMO_LOG=1; }
done
[ "${SHOW_DEMO_LOG:-0}" = "1" ] && tail -20 /tmp/demo.log
pkill -P "$DEMO_PID" 2>/dev/null || true; kill "$DEMO_PID" 2>/dev/null || true

step "4. Hub API (reported, not required: parts of what it loads are not in this repository yet)"
export "$(var CHAT_API_TOKEN)=check-$$" "$(var HUB_API_ALLOW_DEGRADED)=1" "$(var CHAT_API_PORT)=18770"
if python -c 'import sys; sys.path.insert(0, "tools"); import vergil.api' >/tmp/hub.log 2>&1; then ok "the hub API imports"; else echo "   note: the hub API does not import here: $(tail -1 /tmp/hub.log)"; fi

step "5. Names the tree must not carry"
if [ -n "${FORBIDDEN_RE:-}" ]; then
  if grep -rniE "$FORBIDDEN_RE" --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=.next --exclude-dir=.git . | head -5 | grep .; then
    bad "the tree matches the forbidden word list"
  else
    ok "no match"
  fi
else
  ok "no word list given; skipped"
fi

echo
if [ "$FAILED" -eq 0 ]; then echo "CLEAN ROOM CHECK PASSED"; else echo "CLEAN ROOM CHECK FAILED"; fi
exit "$FAILED"
