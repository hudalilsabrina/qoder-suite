#!/usr/bin/env bash
# test-scan-secrets.sh — validasi scan-secrets.sh dengan kasus uji.
# Buat repo uji sementara: 1 yang bersih, 1 yang bocor, pastikan detektor benar.
set -uo pipefail

SCAN="$(cd "$(dirname "$0")" && pwd)/scan-secrets.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0

mk_repo() {  # $1=nama -> buat repo git kosong, set REPO_DIR
  REPO_DIR="$TMP/$1"; mkdir -p "$REPO_DIR"; cd "$REPO_DIR"
  git init -q; git config user.email t@t; git config user.name t
}

check() {  # $1=label $2=expected(clean|dirty) $3=dir
  local label="$1" exp="$2" d="$3" rc=0
  bash "$SCAN" "$d" >/dev/null 2>&1 || rc=1
  local got="clean"; [ "$rc" -ne 0 ] && got="dirty"
  if [ "$got" = "$exp" ]; then
    printf '  \033[32m✓\033[0m %-42s (%s)\n' "$label" "$got"; PASS=$((PASS+1))
  else
    printf '  \033[31m✗\033[0m %-42s harap=%s dapat=%s\n' "$label" "$exp" "$got"; FAIL=$((FAIL+1))
  fi
}

echo "=== TEST: scan-secrets.sh ==="

# --- negatif (harus BERSIH) ---
mk_repo clean1
cat > main.py <<'EOF'
import os
PASSWORD = os.getenv("PASSWORD", "")
UA = "Mozilla/5.0 (Windows NT 10.0) Chrome/131.0.0.0 Safari/537.36"
BASE = "http://127.0.0.1:20127"
def cmd(password=None): return password
EOF
cat > config.example.toml <<'EOF'
[api]
tempmail_base = "http://localhost:8080/api"
EOF
cat > .gitignore <<'EOF'
accounts.txt
config.toml
proxies.txt
data/
EOF
git add -A && git commit -qm init
check "clean repo (UA/placeholder/localhost)" clean "$REPO_DIR"

mk_repo clean2
echo 'print("hello")' > app.py
git add -A && git commit -qm init
check "clean repo (kosong)" clean "$REPO_DIR"

# --- positif (harus ADA TEMUAN) ---
mk_repo dirty_pw
printf 'DEFAULT_PASSWORD = "ExAmPl3#P4ssw0rd"\n' > src.py  # scan-secrets:allow fixture
git add -A && git commit -qm init
check "password hardcoded" dirty "$REPO_DIR"

mk_repo dirty_proxy
printf 'PROXY = "http://exampleuser:examplepass123@p.example-proxy.io:80"\n' > p.py  # scan-secrets:allow fixture
git add -A && git commit -qm init
check "proxy dengan kredensial" dirty "$REPO_DIR"

mk_repo dirty_pat
printf 'token = ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789\n' > k.txt  # scan-secrets:allow fixture
git add -A && git commit -qm init
check "github PAT" dirty "$REPO_DIR"

mk_repo dirty_file
printf 'secret:pass:key\n' > accounts.txt
git add -A && git commit -qm init
check "accounts.txt ter-track" dirty "$REPO_DIR"

mk_repo dirty_history
printf 'PW = "SuperSecret123"\n' > old.py  # scan-secrets:allow fixture
git add -A && git commit -qm add
git rm -q old.py && git commit -qm "remove secret"
check "secret hanya di history (sudah dihapus)" dirty "$REPO_DIR"

mk_repo dirty_key
printf -- '-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----\n' > id_rsa  # scan-secrets:allow fixture
git add -A && git commit -qm init
check "private key ter-track" dirty "$REPO_DIR"

echo ""
echo "HASIL TEST: $PASS lulus, $FAIL gagal"
[ "$FAIL" -eq 0 ] && echo "✅ detektor berfungsi benar" || echo "⚠️ ada kasus yang gagal"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
