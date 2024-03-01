import subprocess
import time

import serial

# open the serial port w/ 9600 baud rate and 0.1 second timeout
ser = serial.Serial("/dev/ttyAMA10", 9600, timeout=0.1)


def get_command(data):
    # convert data to bytes (from hex-formatted string)
    return bytes.fromhex(
        subprocess.run(
            ["./command"] + data, capture_output=True
        )  # run command.c with command data as the arguments
        .stdout.decode("utf-8")  # decode the output from bytes to string
        .strip()  # remove leading/trailing whitespace
    )


def get_response():
    response_str = ser.read(1000).hex()
    response_split = []
    for i in range(0, len(response_str), 2):
        response_split.append(response_str[i : i + 2])

    if response_split[0] != "02":
        print("Invalid response: ", response_split)
        return []

    # length = int(response_split[1], 16)
    length = len(response_split)

    responses = []

    while length > 0:
        # print(response_split)
        # print(responses)
        if response_split[0] == "02":
            data_len = int(response_split[1], 16)
            r = response_split[: data_len + 5]
            response_split = response_split[data_len + 5 :]
            length = len(response_split)

            if r[0] != "02":
                print("Invalid response: ", r)
            else:
                responses.append((r[5], r[6:-2]))
    return responses

    # if (
    #     length != len(response_split) - 5
    # ):  # 1 byte starting char, 2 bytes data length, 2 bytes header CRC
    #     print("Invalid response length")
    #     return None
    # data = response_split[5:-2]
    # if data[0] != "00":
    #     print("Error Code:", data[0])
    #     print("Data:", data[1:])
    #     return None
    # return data[1:]


def get_mifare_1k_uid(response):
    return "".join(response[1][0:4])


def get_type(response):
    return response[1][0]


def send_command(data):
    ser.write(get_command(data))
    return get_response()


def read_card():
    # dummy command to check if the device is connected - should return ACK
    dummy = ["00"]
    # check if the response is the expected ACK
    r = send_command(dummy)
    if len(r) != 1 or r[0][0] != "00" or len(r[0][1]) != 0:
        # TODO: log NFC device not connected
        return None

    read_card_data = ["01", "01", "00", "01", "00", "01"]
    responses = send_command(read_card_data)
    if len(responses) == 1 and responses[0][0] != "00":
        # TODO log "Error Code:", responses[0][0]
        # TODO log "Error Data:", responses[0][1]
        return None
    elif len(responses) == 1:
        responses += get_response()

    if (
        len(responses) < 2
        or responses[1][0] != "08"
        or len(responses[1][1]) < 1
        or responses[1][1][0] != "20"
    ):
        # TODO log print("RFID Command did not end?", responses)
        return None

    # command to read the card type
    read_type_data = ["02", "1E", "00", "01", "00"]
    responses = send_command(read_type_data)

    if len(responses) > 0 and responses[0][0] == "00":
        # print("Card Type:", get_type(responses[0]))
        card_type = get_type(responses[0])
        if card_type == "06":
            # command to output UID of the scanned card
            read_uid_data = ["02", "14", "00", "0A", "00"]
            responses = send_command(read_uid_data)

            for _ in range(10):
                if len(responses) > 0:
                    break
                responses += get_response()
                time.sleep(0.1)

            if responses[0][0] == "00":
                # print("UID:", get_mifare_1k_uid(responses[0]))
                return get_mifare_1k_uid(responses[0])
            else:
                # TODO log error
                # print("Error Code:", responses[0][0])
                # print("Error Data:", responses[0][1])
                return None
        else:
            if card_type != "00":
                # TODO log unsupported card type
                pass
            return False
    else:
        # TODO log error
        return None


if __name__ == "__main__":
    # dummy command to check if the device is connected - should return ACK
    dummy = ["00"]
    # check if the response is the expected ACK
    r = send_command(dummy)
    if len(r) == 1 and r[0][0] == "00" and len(r[0][1]) == 0:
        print("ACK received")
    else:
        print("ACK not received")

    # command to read card data
    read_card_data = ["01", "01", "00", "01", "00", "01"]
    responses = send_command(read_card_data)
    if len(responses) == 1 and responses[0][0] != "00":
        print("Error Code:", responses[0][0])
        print("Error Data:", responses[0][1])
    elif len(responses) == 1:
        responses += get_response()

    if (
        len(responses) < 2
        or responses[1][0] != "08"
        or len(responses[1][1]) < 1
        or responses[1][1][0] != "20"
    ):
        print("RFID Command did not end?", responses)

    # command to read the card type
    read_type_data = ["02", "1E", "00", "01", "00"]
    responses = send_command(read_type_data)
    # print(responses)
    # print(get_type(responses[0]))

    if len(responses) > 0 and responses[0][0] == "00":
        print("Card Type:", get_type(responses[0]))
        if get_type(responses[0]) == "06":
            # command to output UID of the scanned card
            read_uid_data = ["02", "14", "00", "0A", "00"]
            responses = send_command(read_uid_data)
            while len(responses) < 1:
                responses += get_response()

            if responses[0][0] == "00":
                print("UID:", get_mifare_1k_uid(responses[0]))
            else:
                print("Error Code:", responses[0][0])
                print("Error Data:", responses[0][1])

    ser.close()
