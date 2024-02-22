import serial
import subprocess


def get_command(data):
    return bytes.fromhex(
        subprocess.run(["./command"] + data.split(" "), capture_output=True)
        .stdout.decode("utf-8")
        .strip()
    )


ser = serial.Serial("/dev/tty.usbserial-DK0FCC7C", 9600, timeout=1)
# dummy = b"\x02\x03\x00\xAF\xF7\x00\xF0\xE1"
dummy = "00"
# dummy_command = subprocess.run(["./command", dummy], capture_output=True).stdout.decode("utf-8").strip()
# print(dummy_command)
# print(bytes.fromhex(dummy_command))
# ser.write(dummy)
# ser.write(bytes.fromhex(dummy_command))
ser.write(get_command(dummy))
response = ser.read(128).hex()
if response == "020300aff700f0e1":
    print("ACK received")
else:
    print("ACK not received")
    exit(1)

for i in range(0, len(response), 2):
    print(response[i : i + 2], end=" ")
print()

# uid_to_reg = {0x01, 0x01, 0x00, 0x01, 0x00, 0x01}
uid_to_reg = "01 01 00 01 00 01"
# print(get_command(uid_to_reg))
ser.write(get_command(uid_to_reg))
response = ser.read(128).hex()
for i in range(0, len(response), 2):
    print(response[i : i + 2], end=" ")
print()

# uid_from_reg = 0x02, 0x14, 0x00, 0x0A, 0x00
uid_from_reg = "02 14 00 0A 00"
ser.write(get_command(uid_from_reg))
response = ser.read(128).hex()
for i in range(0, len(response), 2):
    print(response[i : i + 2], end=" ")
print()

uid_from_reg = "02 1E 00 01 00"
ser.write(get_command(uid_from_reg))
response = ser.read(128).hex()
for i in range(0, len(response), 2):
    print(response[i : i + 2], end=" ")
print()

ser.close()
