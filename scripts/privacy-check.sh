#!/usr/bin/env bash
# Privacy gate for md2video.
#
# Usage:
#   bash scripts/privacy-check.sh [--full]
#
# Without --full, scans staged files when available. With --full, scans tracked
# repository content. The script blocks known token/private-key/credential
# patterns and warns on likely personal identifiers.

set -euo pipefail

MODE="${1:-}"

blocked=0
warned=0

EXCLUDE=(
  ':!scripts/privacy-check.sh'
  ':!.git/**'
  ':!.venv/**'
  ':!venv/**'
  ':!output/**'
  ':!scenes/**'
  ':!rebuild_animations/**'
  ':!animations/**'
)

run_grep() {
  local pattern="$1"
  if [ "$MODE" = "--full" ]; then
    git grep -n --color=never -P "$pattern" -- "${EXCLUDE[@]}" 2>/dev/null || true
  else
    local files
    files=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null || true)
    if [ -n "$files" ]; then
      echo "$files" | xargs -r git grep -n --color=never -P "$pattern" -- 2>/dev/null || true
    fi
  fi
}

block() {
  local desc="$1"
  local pattern="$2"
  local matches
  matches=$(run_grep "$pattern")
  if [ -n "$matches" ]; then
    echo "[BLOCKED] $desc"
    echo "$matches"
    echo ""
    blocked=$((blocked + $(echo "$matches" | wc -l | tr -d ' ')))
  fi
}

warn() {
  local desc="$1"
  local pattern="$2"
  local matches
  matches=$(run_grep "$pattern")
  if [ -n "$matches" ]; then
    echo "[WARN] $desc"
    echo "$matches"
    echo ""
    warned=$((warned + $(echo "$matches" | wc -l | tr -d ' ')))
  fi
}

echo "md2video Privacy Gate"
echo ""

block "OpenAI API key" 'sk-(proj-)?[A-Za-z0-9]{20,}'
block "GitHub token" 'gh[pousr]_[A-Za-z0-9_]{30,}'
block "Slack token" 'xox[baprs]-[A-Za-z0-9-]{10,}'
block "AWS access key" 'AKIA[0-9A-Z]{16}'
block "Private key" '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'
block "JWT token" 'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]{10,}'
block "Credential assignment" '(SECRET|TOKEN|PASSWORD|API_KEY|APP_SECRET|ACCESS_KEY)\s*=\s*["'\''"]?[A-Za-z0-9!@#$%^&*()_+\-]{8,}["'\''"]?'
block "Internal IP" '(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})'
block "Local absolute user path in tracked text" '/Users/[A-Za-z0-9._-]+/'

warn "Personal email" '[A-Za-z0-9._%+-]+@(?!example\.com|test\.com|localhost)[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
warn "CN mobile phone" '1[3-9][0-9]{9}'
warn "WeChat payload-like URL" '(weixin://|wecom://|https?://[^[:space:]"'\''<>]*(mp\.weixin\.qq\.com|work\.weixin\.qq\.com|u\.wechat\.com)[^[:space:]"'\''<>]*)'

echo ""
if [ "$blocked" -gt 0 ]; then
  echo "Privacy gate failed: $blocked blocking finding(s)"
  exit 1
fi

if [ "$warned" -gt 0 ]; then
  echo "Privacy gate passed with $warned warning finding(s)"
else
  echo "Privacy gate passed"
fi
