import serial
import subprocess


def get_command(data):
    # convert data to bytes (from hex-formatted string)
    return bytes.fromhex(
        subprocess.run(
            ["./command"] + data, capture_output=True
        )  # run command.c with command data as the arguments
        .stdout.decode("utf-8")  # decode the output from bytes to string
        .strip()  # remove leading/trailing whitespace
    )


def get_response(response_str):
    response_split = []
    for i in range(0, len(response_str), 2):
        response_split.append(response_str[i : i + 2])
    if response_split[0] != "02":
        print("Invalid response")
        return None
    length = int(response_split[1], 16)
    if (
        length != len(response_split) - 5
    ):  # 1 byte starting char, 2 bytes data length, 2 bytes header CRC
        print("Invalid response length")
        return None
    data = response_split[5:-2]
    if data[0] != "00":
        print("Error Code:", data[0])
        print("Data:", data[1:])
        return None
    return data[1:]


def get_mifare_1k_uid(response):
    return "".join(response[0:4])


def get_type(response):
    return response[0]


# open the serial port w/ 9600 baud rate and 1 second timeout
ser = serial.Serial("/dev/tty.usbserial-DK0FCC7C", 9600, timeout=1)

# dummy command to check if the device is connected - should return ACK
dummy = ["00"]
# get the command as bytes and write it to the serial port
ser.write(get_command(dummy))
# read the response from the serial port and convert it to a hex-formatted string
response = ser.read(128).hex()
response = get_response(response)
# check if the response is the expected ACK
if response == []:
    print("ACK received")
else:
    print("ACK not received")
    exit(1)

# print the response in hex-formatted string
# for i in range(0, len(response), 2):
#     print(response[i : i + 2], end=" ")
# print()

# command to read card data
read_card = ["01", "01", "00", "01", "00", "01"]
ser.write(get_command(read_card))
response = ser.read(128).hex()
# for i in range(0, len(response), 2):
#     print(response[i : i + 2], end=" ")
# print()
# response = get_response(response)

# command to read the card type
read_type = ["02", "1E", "00", "01", "00"]
ser.write(get_command(read_type))
response = ser.read(128).hex()
# for i in range(0, len(response), 2):
#     print(response[i : i + 2], end=" ")
# print()
response = get_response(response)

if response is not None:
    print("Card Type:", get_type(response))
    if get_type(response) == "06":
        # command to output UID of the scanned card
        read_uid = ["02", "14", "00", "0A", "00"]
        ser.write(get_command(read_uid))
        response = ser.read(128).hex()
        # for i in range(0, len(response), 2):
        #     print(response[i : i + 2], end=" ")
        # print()
        response = get_response(response)
        print("UID:", get_mifare_1k_uid(response))


ser.close()
