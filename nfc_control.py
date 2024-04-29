import subprocess
import time
from multiprocessing import Process, Queue

import serial  # type: ignore

# delay between reads for the same card
DELAY = 1

# open the serial port w/ 9600 baud rate and 0.1 second timeout
ser = serial.Serial("/dev/ttyUSB0", 9600, timeout=0.1)

# TODO: when refreshing the database from the sheet, clear the timestamps (otherwise this will fill up & take a lot of memory)
# maintain the last scanned time for each card id so that we can prevent multiple scans within a short time
timestamps = {}


def get_command(data):
    # convert data to bytes (from hex-formatted string)
    return bytes.fromhex(
        subprocess.run(
            ["./nfc/command"] + data, capture_output=True
        )  # run command.c with command data as the arguments
        .stdout.decode("utf-8")  # decode the output from bytes to string
        .strip()  # remove leading/trailing whitespace
    )


def get_response():
    response_str = ser.read(1000).hex()
    if len(response_str) < 2:
        return []
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
    response = "".join(response[1][0:4])
    if response in timestamps and time.time() - timestamps[response] < DELAY:
        return False
    timestamps[response] = time.time()
    return response


def get_type(response):
    return response[1][0]


def send_command(data):
    ser.write(get_command(data))
    return get_response()


def check_connection():
    # dummy command to check if the device is connected - should return ACK
    dummy = ["00"]
    # check if the response is the expected ACK
    r = send_command(dummy)
    if len(r) != 1 or r[0][0] != "00" or len(r[0][1]) != 0:
        # TODO: log NFC device not connected
        return False
    return True


def read_card():
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
        print(responses)
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


def read_card_queue(q):
    q.put(read_card())


def read_card_queue_timeout(time):
    """
    Call read_card() with a timeout

    time: float: the time limit in seconds

    Returns None if there was an error, or passes through the return value of read_card()
    """
    q = Queue()
    p = Process(target=read_card_queue, args=(q,))
    p.start()
    p.join(time)
    if p.is_alive():
        p.terminate()
        return None

    return q.get().upper()


def close():
    ser.close()


if __name__ == "__main__":
    if not check_connection():
        print("NFC device not connected")
        exit(1)
    while True:
        try:
            print(read_card())
        except KeyboardInterrupt:
            close()
            raise
