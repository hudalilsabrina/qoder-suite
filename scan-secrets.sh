#!/usr/bin/env bash
# scan-secrets.sh — deteksi data sensitif sebelum publish ke repo publik.
#
# Pakai:
#   ./scan-secrets.sh                 # scan repo di cwd
#   ./scan-secrets.sh /path/to/repo   # scan repo tertentu
#
# Cek DUA lapis:
#   1. working tree  → HANYA file yang ter-track (yang benar-benar akan naik)
#   2. git history   → SEMUA commit (file yang sudah dihapus pun tetap ketahuan)
#
# Keluaran: CRITICAL = jangan publish (exit 1). INFO = catatan, boleh diabaikan.
set -uo pipefail

REPO="${1:-.}"
cd "$REPO" 2>/dev/null || { echo "✗ direktori tidak ditemukan: $REPO" >&2; exit 2; }

RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; CYA=$'\033[36m'; DIM=$'\033[2m'; RST=$'\033[0m'
CRIT=0; INFO=0

say()  { printf '%s\n' "$*"; }
hdr()  { printf '\n%s== %s ==%s\n' "$CYA" "$*" "$RST"; }
crit() { printf '%s  ✗ CRITICAL: %s%s\n' "$RED" "$*" "$RST"; CRIT=$((CRIT+1)); }
info() { printf '%s  · info: %s%s\n' "$DIM" "$*" "$RST"; INFO=$((INFO+1)); }
ok()   { printf '%s  ✓ %s%s\n' "$GRN" "$*" "$RST"; }

# -------------------------------------------------------------------- pola
# CRITICAL: kredensial nyata / kunci privat / proxy ber-auth / token
CRIT_PATTERNS=(
  "password-hardcoded|(password|passwd|passphrase|pwd|pw|DEFAULT_PASSWORD|api_?key|apikey|auth_token|access_token)[\"']?[[:space:]]*[:=][[:space:]]*[\"'][A-Za-z0-9!@#%^&*_+.-]{8,}[\"']"
  "private-key|BEGIN (RSA|OPENSSH|EC|DSA|PGP) PRIVATE KEY"
  "github-pat|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|gho_[A-Za-z0-9]{20,}|ghs_[A-Za-z0-9]{20,}"
  "openai-key|sk-[A-Za-z0-9]{32,}"
  "anthropic-key|sk-ant-[A-Za-z0-9_-]{20,}"
  "aws-key|AKIA[0-9A-Z]{16}"
  "slack-token|xox[baprs]-[A-Za-z0-9-]{10,}"
  "jwt-token|eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}"
  "proxy-with-auth|https?://[A-Za-z0-9._-]+:[^/@[:space:]]{5,}@[A-Za-z0-9.-]+"
  "telegram-id|chat_id[\"']?[[:space:]]*[:=][[:space:]]*[\"']?[0-9]{8,}"
  "ssh-key-material|ssh-(rsa|ed25519)[[:space:]]+AAAAB3"
)
# INFO: kemungkinan sensitif tapi sering false-positive / tidak berbahaya
INFO_PATTERNS=(
  "app-secret-hardcoded|secret[\"']?[[:space:]]*[:=][[:space:]]*[\"'][^\"']{8,}[\"']"
  "localhost-endpoint|(127\\.0\\.0\\.1|localhost):[0-9]{2,5}"
  "webshare|webshare\\.io"
  "bearer-hardcoded|Bearer[[:space:]]+[A-Za-z0-9._-]{20,}"
)

# file/dir yang TIDAK BOLEH ter-track
FORBIDDEN='(^|/)(accounts\.txt|config\.toml|proxies?[^/]*\.(txt|json)|\.env[^/]*|.*\.(pem|key|p12|pfx)|id_rsa[^/]*|diag_.*\.py|cookies?\.txt)$|(^|/)data/'

# baris yang selalu diabaikan (UA browser, contoh, placeholder, template, env-read)
IGNORE_LINE='(Mozilla/|Chrome/[0-9]|Safari/[0-9]|Firefox/[0-9]|AppleWebKit|example\.com|placeholder|your[_-]|xxxx|<[a-z_]+>|\.\.\.|redacted|type=["'\'']|input\[|os\.getenv|get_cfg|os\.environ)'

# -------------------------------------------------------- 1. WORKING TREE
hdr "1. Working tree (file ter-track)"
if git rev-parse --git-dir >/dev/null 2>&1; then
  FILES="$(git ls-files)"; MODE="tracked"
else
  FILES="$(find . -type f -not -path './.git/*' -not -path './.venv/*' -not -path '*/node_modules/*')"
  MODE="semua file (bukan git repo)"
fi
say "${DIM}  $(printf '%s\n' "$FILES" | grep -c .) file ($MODE)${RST}"

# 1a. nama file terlarang
BADF="$(printf '%s\n' "$FILES" | grep -Ei "$FORBIDDEN" || true)"
if [ -n "$BADF" ]; then
  while IFS= read -r f; do [ -n "$f" ] && crit "file sensitif ter-track: $f"; done <<< "$BADF"
else
  ok "tidak ada file sensitif ter-track"
fi

# 1b. pola di isi file
# Baris dengan marker "scan-secrets:allow" (atau "# nosec") dilewati — pakai
# HANYA untuk fixture test / contoh yang sengaja memuat pola palsu.
scan_files() {  # $1=label $2=regex $3=level(crit|info)
  local label="$1" rx="$2" lvl="$3" out
  out="$(printf '%s\n' "$FILES" | while IFS= read -r f; do
           [ -f "$f" ] || continue
           grep -HniIE -- "$rx" "$f" 2>/dev/null
         done | grep -vE "$IGNORE_LINE" | grep -vE 'scan-secrets:allow|# *nosec' || true)"
  [ -z "$out" ] && return
  while IFS= read -r l; do
    [ -z "$l" ] && continue
    if [ "$lvl" = crit ]; then crit "[$label] ${l:0:150}"; else info "[$label] ${l:0:130}"; fi
  done <<< "$(printf '%s\n' "$out" | head -5)"
}
for e in "${CRIT_PATTERNS[@]}"; do scan_files "${e%%|*}" "${e#*|}" crit; done
for e in "${INFO_PATTERNS[@]}"; do scan_files "${e%%|*}" "${e#*|}" info; done

# -------------------------------------------------------- 2. GIT HISTORY
if git rev-parse --git-dir >/dev/null 2>&1; then
  hdr "2. Git history (semua commit)"
  EVER="$(git log --all --pretty=format: --name-only 2>/dev/null | sort -u | grep -v '^$' || true)"
  BADEVER="$(printf '%s\n' "$EVER" | grep -Ei "$FORBIDDEN" || true)"
  if [ -n "$BADEVER" ]; then
    while IFS= read -r f; do [ -n "$f" ] && crit "file sensitif PERNAH ada di history: $f"; done <<< "$BADEVER"
  else
    ok "tidak ada file sensitif di history"
  fi
  for e in "${CRIT_PATTERNS[@]}"; do
    label="${e%%|*}"; rx="${e#*|}"
    out="$(git grep -niE -- "$rx" $(git rev-list --all 2>/dev/null) 2>/dev/null \
          | grep -vE "$IGNORE_LINE" | grep -vE 'scan-secrets:allow|# *nosec' | head -3 || true)"
    [ -z "$out" ] && continue
    while IFS= read -r l; do [ -n "$l" ] && crit "[history:$label] ${l:0:150}"; done <<< "$out"
  done
  ok "selesai memindai history"
else
  hdr "2. Git history"; info "bukan git repo — dilewati"
fi

# ------------------------------------------------------------------- HASIL
hdr "HASIL"
if [ "$CRIT" -eq 0 ]; then
  printf '%s✅ BERSIH — aman untuk publish.%s  %s(%d catatan info)%s\n' "$GRN" "$RST" "$DIM" "$INFO" "$RST"
  exit 0
else
  printf '%s⚠️  %d TEMUAN CRITICAL — JANGAN publish.%s  %s(%d info)%s\n' "$RED" "$CRIT" "$RST" "$DIM" "$INFO" "$RST"
  printf '\n%sBersihkan history:\n' "$DIM"
  printf "  git filter-branch -f --index-filter \\\\\n"
  printf "    'git rm --cached --ignore-unmatch <file>' --prune-empty -- --all\n"
  printf '  rm -rf .git/refs/original && git reflog expire --expire=now --all && git gc --prune=now\n'
  printf '  git push --force%s\n' "$RST"
  exit 1
fi
