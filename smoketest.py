from src.bambu_printers.bambu_account import get_account
from paho.mqtt import client as mqtt
import ssl

a = get_account()
devices = a.get_devices()
name = next(iter(devices.keys()))
dev_id = devices[name]
pw = a.get_device_access_code(dev_id) or a.get_token()
user = a.get_username() or a.email

c = mqtt.Client(client_id=dev_id, protocol=mqtt.MQTTv311, clean_session=True)
c.username_pw_set(username=user, password=pw)
c.tls_set(cert_reqs=ssl.CERT_REQUIRED)
print(f"Connecting to us.mqtt.bambulab.com:8883 as {dev_id} user={user} pw={'dev_access_code' if pw!=a.get_token() else 'token'}")
rc = c.connect("us.mqtt.bambulab.com", 8883, 60)
print("RC:", rc)
