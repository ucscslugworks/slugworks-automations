# mqtt_discover_and_verify.py
import os, ssl, time, base64, json, sys
import requests
import paho.mqtt.client as mqtt

API = "https://api.bambulab.com/v1"
HOSTS = [
    os.environ.get("MQTT_HOST") or "us.mqtt.bambulab.com",
    "mqtt.bambulab.com",
    "eu.mqtt.bambulab.com",
    "sg.mqtt.bambulab.com",
]

TOKEN  = "--"   # required: access token (Bearer)
EMAIL  = "slugworks@ucsc.edu"   # optional but recommended
SERIAL = os.environ.get("SERIAL")  # optional: limit checks to one dev_id

if not TOKEN:
    print("Set TOKEN env var to your Bearer access token.")
    sys.exit(1)

def b64url_json(s):
    try:
        parts = s.split(".")
        if len(parts) < 2: return {}
        pad = "=" * ((4 - len(parts[1]) % 4) % 4)
        return json.loads(base64.urlsafe_b64decode(parts[1] + pad))
    except Exception:
        return {}

def get_devices():
    r = requests.get(f"{API}/iot-service/api/user/bind",
                     headers={"Authorization": f"Bearer {TOKEN}"}, timeout=20)
    r.raise_for_status()
    devices = r.json().get("devices", [])
    out = []
    for d in devices:
        out.append({
            "name": d.get("name"),
            "dev_id": d.get("dev_id"),
            "online": d.get("online"),
            # These often exist and can be useful:
            "dev_model_name": d.get("dev_model_name") or d.get("model"),
            "dev_product_name": d.get("dev_product_name"),
            "dev_access_code": (d.get("dev_access_code") or "").strip()
        })
    return out

def username_candidates(token_claims, email_hint=None):
    cands = []
    for k in ("username","email","uid","userId","sub"):
        v = token_claims.get(k)
        if isinstance(v, str) and v and v not in cands:
            cands.append(v)
    if email_hint and email_hint not in cands:
        cands.append(email_hint)
    return cands

def try_mqtt(host, client_id, user, password):
    outcome = {"host":host, "client_id":client_id, "user":user, "rc":None, "err":None}
    def on_connect(client, userdata, flags, rc, properties=None):
        outcome["rc"] = rc
        client.disconnect()
    client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311, clean_session=True)
    client.username_pw_set(user, password)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.tls_insecure_set(False)
    client.on_connect = on_connect
    try:
        client.connect(host, 8883, keepalive=60)
        client.loop_start()
        for _ in range(10):
            if outcome["rc"] is not None: break
            time.sleep(0.3)
    except Exception as e:
        outcome["err"] = f"{type(e).__name__}: {e}"
    finally:
        try: client.loop_stop(); client.disconnect()
        except: pass
    return outcome

claims = b64url_json(TOKEN)
users = username_candidates(claims, EMAIL)
if not users and EMAIL: users = [EMAIL]

print("JWT claims (useful):", {k: claims.get(k) for k in ("username","email","uid","userId","sub","iss","aud")})

devices = get_devices()
if SERIAL:
    devices = [d for d in devices if d["dev_id"] == SERIAL] or devices

if not devices:
    print("No devices returned from /iot-service/api/user/bind. Check TOKEN.")
    sys.exit(2)

print("\nDiscovered devices:")
for d in devices:
    print(f"- {d['name']}: dev_id={d['dev_id']} online={d['online']} access_code={'<present>' if d['dev_access_code'] else '<missing>'}")

# Try for each device: passwords = [TOKEN, dev_access_code], users = [candidates]
for d in devices:
    client_id = d["dev_id"]
    pw_options = [("token", TOKEN)]
    if d["dev_access_code"]:
        pw_options.append(("dev_access_code", d["dev_access_code"]))

    for host in HOSTS:
        for user in users:
            for label, pw in pw_options:
                res = try_mqtt(host, client_id, user, pw)
                print(f"host={host} client_id={client_id} user={user} pw={label} rc={res['rc']} err={res['err'] or ''}")
                # rc meanings: 0 OK, 1 bad protocol, 2 bad client_id, 4 bad username/password, 5 not authorized
                if res["rc"] == 0:
                    print("\n✅ MQTT OK — use this config:")
                    print(f"  host       : {host}")
                    print(f"  client_id  : {client_id}  (exact dev_id)")
                    print(f"  username   : {user}")
                    print(f"  password   : {label}  (use the same {label} you just used)")
                    sys.exit(0)

print("\n❌ No combo worked.")
print("Hints:")
print("- rc=2 => client_id wrong: must equal dev_id exactly as returned by /user/bind.")
print("- rc=4/5 => credentials rejected: try another username candidate (email vs uid) or refresh TOKEN.")
print("- If token works for REST but not MQTT, sometimes dev_access_code is required as the MQTT password.")
