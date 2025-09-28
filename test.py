# save as mqtt_verify.py
import os, ssl, sys, time
import paho.mqtt.client as mqtt

HOST   = os.environ.get("MQTT_HOST", "us.mqtt.bambulab.com")  # try eu.mqtt.bambulab.com if you're in EU
PORT   = int(os.environ.get("MQTT_PORT", "8883"))
EMAIL  = "slugworks@ucsc.edu"          # your Bambu login email
TOKEN  = "TOKEN="          # the bearer access token you use for REST
SERIAL = ""         # e.g.  (dev_id from /iot-service/api/user/bind)

TOPICS = [f"device/{SERIAL}/report", f"device/{SERIAL}/sys_status"]

def on_connect(client, userdata, flags, rc, properties=None):
    print("on_connect rc:", rc)
    if rc == 0:
        for t in TOPICS:
            print("subscribing:", t)
            client.subscribe(t, qos=0)
    elif rc == 4:
        print("Not authorized (check EMAIL/TOKEN).")
    elif rc == 2:
        print("Client identifier not valid (check SERIAL used as client_id).")

def on_message(client, userdata, msg):
    print("message:", msg.topic, msg.payload[:200])
    client.disconnect()

def main():
    client = mqtt.Client(
        client_id=SERIAL,              # IMPORTANT: must be the printer's serial
        protocol=mqtt.MQTTv311,        # v3.1.1 (v5 often gets rejected)
        clean_session=True,
    )
    client.username_pw_set(EMAIL, TOKEN)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)   # system CAs
    client.tls_insecure_set(False)

    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to {HOST}:{PORT} as client_id={SERIAL}, user={EMAIL} …")
    client.connect(HOST, PORT, keepalive=60)
    client.loop_start()

    # wait a bit for a message; if none, you may still be connected OK
    for _ in range(30):
        time.sleep(1)
    client.loop_stop()
    client.disconnect()
    print("Done.")

if __name__ == "__main__":
    main()
