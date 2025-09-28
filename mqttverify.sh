
#!/usr/bin/env bash
set -euo pipefail

API="https://api.bambulab.com/v1"
TOKEN="${TOKEN:-}"

if [[ -z "$TOKEN" ]]; then
  echo "Usage: TOKEN=<access_token> $0" >&2
  exit 1
fi

# Try a few user-info endpoints; print the first username-like field we find.
endpoints=(
  "user-service/my/userInfo"
  "user-service/my/baseinfo"
  "user-service/my/info"
  "user-service/my/profile"
)

for ep in "${endpoints[@]}"; do
  echo "Trying $ep..." >&2
  if resp="$(curl -sfS -H "Authorization: Bearer $TOKEN" "$API/$ep")"; then
    username="$(jq -r '.username // .userName // .user_id // .userId // empty' <<<"$resp")"
    if [[ -n "$username" && "$username" != "null" ]]; then
      echo "$username"
      exit 0
    fi
  fi
done

echo "Could not find username from known endpoints." >&2
exit 2
