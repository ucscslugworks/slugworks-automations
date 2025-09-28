# Use the refreshToken from bambu.json
REFRESH=''

curl -sS https://api.bambulab.com/v1/user-service/user/refreshtoken \
  -H 'Content-Type: application/json' \
  -d "{\"refreshToken\":\"$REFRESH\"}" | tee /tmp/refresh.json

# Extract the JWT accessToken
ACCESS_TOKEN=$(jq -r '.accessToken' /tmp/refresh.json)

# sanity check: JWTs have dots
echo "$ACCESS_TOKEN"
# should look like: ...
