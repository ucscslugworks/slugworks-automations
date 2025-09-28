#!/usr/bin/env bash
set -euo pipefail

# ========= CONFIG (set here or export as env) =========
EMAIL="${EMAIL:-slugworks@ucsc.edu}"
PASS="${PASS:-WorkingNine2Five!}"
CODE="${CODE:-}"                                # optional 2FA code if required

UA="${UA:-Mozilla/5.0}"
OUT_JSON="${OUT_JSON:-common/bambu.json}"
COOKIEJAR="${COOKIEJAR:-cookies.txt}"

# Separate origins per your constants:
LOGIN_ORIGIN="${LOGIN_ORIGIN:-https://bambulab.com}"
API_ORIGIN="${API_ORIGIN:-https://api.bambulab.com}"

# Optional Cloudflare clearances (each hostname has its own):
CF_CLEARANCE_LOGIN="${CF_CLEARANCE_LOGIN:-}"    # cf_clearance for bambulab.com
CF_CLEARANCE_API="${CF_CLEARANCE_API:-}"        # cf_clearance for api.bambulab.com

# Endpoints (exactly as you provided)
LOGIN_URL="$LOGIN_ORIGIN/api/sign-in/form"
CODE_URL="$LOGIN_ORIGIN/api/sign-in/code"
REFRESH_URL="$API_ORIGIN/v1/user-service/user/refreshtoken"
TASKS_URL="$API_ORIGIN/v1/user-service/my/tasks"
DEVICES_URL="$API_ORIGIN/v1/iot-service/api/user/bind"

mkdir -p "$(dirname "$OUT_JSON")"

say() { printf '%s\n' "$*" >&2; }

have_cookie() {
  local name="$1"
  [[ -f "$COOKIEJAR" ]] || return 1
  awk -v n="$name" '$6==n {found=1} END{exit(found?0:1)}' "$COOKIEJAR" 2>/dev/null
}

get_cookie_val() {
  local name="$1"
  [[ -f "$COOKIEJAR" ]] || { echo ""; return; }
  awk -v n="$name" '$6==n {val=$7} END{print val}' "$COOKIEJAR" 2>/dev/null
}

write_json() {
  local token="$1" refresh="$2"
  [[ -n "$token" && -n "$refresh" ]] || { say "[!] Missing token/refreshToken"; exit 1; }
  cat >"$OUT_JSON" <<EOF
{
  "token": "$token",
  "refreshToken": "$refresh"
}
EOF
  say "[*] Wrote tokens to $OUT_JSON"
}

warmup_login_host() {
  [[ -z "$CF_CLEARANCE_LOGIN" ]] && return 0
  say "[*] Priming login host with cf_clearance (bambulab.com)…"
  curl -sS --compressed -L \
    -c "$COOKIEJAR" -b "$COOKIEJAR" \
    -H "User-Agent: $UA" \
    -H "Cookie: cf_clearance=$CF_CLEARANCE_LOGIN" \
    "$LOGIN_ORIGIN/" >/dev/null || true
}

warmup_api_host() {
  [[ -z "$CF_CLEARANCE_API" ]] && return 0
  say "[*] Priming API host with cf_clearance (api.bambulab.com)…"
  curl -sS --compressed -L \
    -c "$COOKIEJAR" -b "$COOKIEJAR" \
    -H "User-Agent: $UA" \
    -H "Cookie: cf_clearance=$CF_CLEARANCE_API" \
    "$API_ORIGIN/" >/dev/null || true
}

login() {
  say "[*] Logging in at $LOGIN_URL (JSON body)…"
  warmup_login_host
  # Send JSON as required; save cookies
  curl -sS --compressed -i \
    -c "$COOKIEJAR" -b "$COOKIEJAR" \
    -H "User-Agent: $UA" \
    -H "Content-Type: application/json" \
    ${CF_CLEARANCE_LOGIN:+-H "Cookie: cf_clearance=$CF_CLEARANCE_LOGIN"} \
    -d "{\"account\":\"$EMAIL\",\"password\":\"$PASS\",\"apiError\":\"\"}" \
    "$LOGIN_URL" >/dev/null || true

  if have_cookie token && have_cookie refreshToken; then
    return 0
  fi

  # If 2FA is required, you must POST /api/sign-in/code with code=
  if [[ -n "$CODE" ]]; then
    say "[*] Submitting 2FA code at $CODE_URL…"
    curl -sS --compressed -i \
      -c "$COOKIEJAR" -b "$COOKIEJAR" \
      -H "User-Agent: $UA" \
      -H "Content-Type: application/json" \
      ${CF_CLEARANCE_LOGIN:+-H "Cookie: cf_clearance=$CF_CLEARANCE_LOGIN"} \
      -d "{\"account\":\"$EMAIL\",\"password\":\"$PASS\",\"code\":\"$CODE\",\"apiError\":\"\"}" \
      "$CODE_URL" >/dev/null || true
  fi

  if ! have_cookie token || ! have_cookie refreshToken; then
    say "[!] Login did not yield token/refreshToken cookies."
    say "    Tips:"
    say "    - Ensure Content-Type is application/json (this script does it)."
    say "    - If Cloudflare blocks, set CF_CLEARANCE_LOGIN (and CF_CLEARANCE_API for API calls)."
    exit 1
  fi
}

refresh() {
  say "[*] Refreshing via $REFRESH_URL…"
  warmup_api_host
  local refresh_val; refresh_val="$(get_cookie_val refreshToken)"
  [[ -n "$refresh_val" ]] || { say "[!] No refreshToken cookie; need login."; return 1; }

  curl -sS --compressed \
    -c "$COOKIEJAR" -b "$COOKIEJAR" \
    -H "User-Agent: $UA" \
    -H "Content-Type: application/json" \
    ${CF_CLEARANCE_API:+-H "Cookie: cf_clearance=$CF_CLEARANCE_API"} \
    -d "{\"refreshToken\":\"$refresh_val\"}" \
    "$REFRESH_URL" >/dev/null || true

  if ! have_cookie token || ! have_cookie refreshToken; then
    say "[!] Refresh did not update tokens; will re-login."
    return 1
  fi
}

check_and_save() {
  local token refresh
  token="$(get_cookie_val token)"
  refresh="$(get_cookie_val refreshToken)"
  write_json "$token" "$refresh"

  say "[*] Verifying /my/tasks with Authorization: Bearer…"
  curl -sS --compressed \
    -b "$COOKIEJAR" \
    -H "User-Agent: $UA" \
    -H "Authorization: Bearer $token" \
    "$TASKS_URL" | head -c 400 | sed 's/^/    /'
  say "[*] Done."
}

# ================= MAIN =================
touch "$COOKIEJAR"

if have_cookie token && have_cookie refreshToken; then
  # Try refresh first; fallback to full login
  if ! refresh; then
    login
  fi
else
  login
fi

check_and_save
