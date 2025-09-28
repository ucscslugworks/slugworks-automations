# mqtt_verify_combo.py
import os, ssl, time, base64, json
import paho.mqtt.client as mqtt

SERIAL = os.environ["SERIAL"]            # e.g.   (from /iot-service/api/user/bind)
EMAIL  = os.environ["EMAIL"]             # your Bambu login email
TOKEN  = "token="             # the access token you used for REST

HOSTS = [
    os.environ.get("MQTT_HOST") or "us.mqtt.bambulab.com",
    "mqtt.bambulab.com",
    "eu.mqtt.bambulab.com",
    "sg.mqtt.bambulab.com",
]

def decode_jwt_noverify(tok: str):
    try:
        parts = tok.split(".")
        payload = parts[1] + "==="
        payload = payload[: len(payload) - (len(payload) % 4)]  # pad base64url
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}

claims = decode_jwt_noverify(TOKEN)
candidates_user = []
for k in ("username","email","uid","userId","sub"):
    v = claims.get(k)
    if isinstance(v, str) and v and v not in candidates_user:
        candidates_user.append(v)
# Always try your login email as well
if EMAIL not in candidates_user:
    candidates_user.insert(0, EMAIL)

TOPICS = [f"device/{SERIAL}/report", f"device/{SERIAL}/sys_status"]

def try_once(host, user):
    outcome = {"host": host, "user": user, "rc": None, "note": ""}
    def on_connect(client, userdata, flags, rc, properties=None):
        outcome["rc"] = rc
        if rc == 0:
            for t in TOPICS:
                client.subscribe(t, 0)
        client.disconnect()

    client = mqtt.Client(client_id=SERIAL, protocol=mqtt.MQTTv311, clean_session=True)
    client.username_pw_set(user, TOKEN)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.tls_insecure_set(False)
    client.on_connect = on_connect

    try:
        client.connect(host, 8883, keepalive=60)
        client.loop_start()
        for _ in range(8):
            if outcome["rc"] is not None:
                break
            time.sleep(0.5)
    except Exception as e:
        outcome["note"] = f"connect error: {e.__class__.__name__}: {e}"
    finally:
        try:
            client.loop_stop(); client.disconnect()
        except: pass
    return outcome

print("JWT claims (useful bits):", {k: claims.get(k) for k in ("username","email","uid","userId","sub","iss","aud")})

for host in HOSTS:
    for user in candidates_user:
        out = try_once(host, user)
        print(f"host={out['host']} user={out['user']} rc={out['rc']} {out['note']}")
        # rc meanings: 0 OK, 1 bad protocol, 2 bad client_id, 4 bad username/password, 5 not authorized
        if out["rc"] == 0:
            print("\n✅ Connected! Use these settings in your app:")
            print(f"  MQTT host   : {host}")
            print(f"  client_id   : {SERIAL}")
            print(f"  username    : {user}")
            print(f"  password    : <YOUR TOKEN>")
            raise SystemExit(0)

print("\n❌ No combination worked.")
print("Hints:")
print("- rc=2 => client_id wrong: SERIAL must equal dev_id (from /iot-service/api/user/bind).")
print("- rc=4/5 => token not accepted for MQTT (expired, or web token without MQTT scope).")
print("- Try a fresh token and re-run; ensure no trailing spaces/newlines in TOKEN.")
