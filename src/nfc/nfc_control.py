import subprocess
import time
from multiprocessing import Process, Queue

import serial  # type: ignore

# https://eccel.co.uk/product/chilli-usb-b1/ - product page for the USB NFC reader
# https://eccel.co.uk/wp-content/downloads/USB-B1-v2-User-manual.pdf - user manual for the USB NFC reader
# https://eccel.co.uk/wp-content/downloads/RFID-B1-User-Manual.pdf - user manual for a different NFC reader, contains all the commands for the USB NFC reader

# delay between reads for the same card
DELAY = 0.1

# open the serial port w/ 9600 baud rate and 0.1 second timeout
ser = serial.Serial("/dev/ttyUSB0", 9600, timeout=0.1)

# maintain the last scanned time for each card id so that we can prevent multiple scans within a short time
timestamps = {}


# use the command.c file to get the hex string for the command to send to the NFC reader
def get_command(data):
    # convert data to bytes (from hex-formatted string)
    return bytes.fromhex(
        subprocess.run(
            ["./nfc/command"] + data, capture_output=True
        )  # run command.c with command data as the arguments
        .stdout.decode("utf-8")  # decode the output from bytes to string
        .strip()  # remove leading/trailing whitespace
    )


#
def get_response():
    # get string response from nfc reader over serial connection (max 1000 bytes)
    # this is read as a hex string
    response_str = ser.read(1000).hex()

    # if the response is empty, return an empty list
    # first char is the response type, second char onward is the response data
    if len(response_str) < 2:
        return []

    # split the response into 2-character chunks
    response_split = []
    for i in range(0, len(response_str), 2):
        response_split.append(response_str[i : i + 2])

    # packet must start with 0x02 - reference RFID-B1 manual 4.5.1.1
    if response_split[0] != "02":
        print("Invalid response: ", response_split)
        return []

    # get length of the response data
    length = len(response_split)

    responses = []

    # loop through the response data - in case multiple scans occur at once
    while length > 0:
        # if the first byte is 0x02, then the response is valid
        if response_split[0] == "02":
            # get the length of the data - second and third bytes (should only be 1 byte)
            data_len = int(response_split[1], 16)

            # get this response - data_len + 5 bytes (0x02, data_len LSB, data_len MSB, Header CRC LSB, Header CRC MSB, data_len bytes of data) - RFID-B1 manual 4.5.1.1
            r = response_split[: data_len + 5]

            # remove this response from the serial data
            response_split = response_split[data_len + 5 :]

            # update the length of the serial data
            length = len(response_split)

            # if the response does not start with 0x02, then it is invalid
            if r[0] != "02":
                print("Invalid response: ", r)
            else:
                # the first byte of the data is the error code, the rest is the data
                # TODO: why are the last 2 bytes dropped?
                responses.append((r[5], r[6:-2]))
        else:
            # if the response does not start with 0x02, then it is invalid
            print("Invalid response: ", response_split)
            break
    return responses


# given an array response, return the UID of a Mifare 1k card and update the timestamp
def get_mifare_1k_uid(response):
    # the UID is the first 4 bytes of the data
    response = "".join(response[1][0:4])

    # if the response is in the timestamps and the time since the last scan is less than the delay, return False
    if response in timestamps and time.time() - timestamps[response] < DELAY:
        return False

    # update the timestamp
    timestamps[response] = time.time()

    # return the UID in uppercase
    return response.upper()


# get the type of the card from the response
def get_type(response):
    return response[1][0]


# send a command to the NFC reader and get the response
def send_command(data):
    ser.write(get_command(data))
    return get_response()


# check if the NFC device is connected
def check_connection():
    # dummy command to check if the device is connected - should return ACK
    dummy = ["00"]

    # check if the response is the expected ACK
    r = send_command(dummy)

    # if the response is not the expected ACK, then the NFC device is not connected (ACK is 0x00)
    if len(r) != 1 or r[0][0] != "00" or len(r[0][1]) != 0:
        # TODO: log NFC device not connected
        return False
    return True


# full process of reading the card and returning the UID
def read_card():
    # command to read the card data
    # 01: write to rfid memory - RFID-B1 manual 5.3.2
    # 00 01: memory address for command register - RFID-B1 manual 3.3
    # 00 01: length of data to write (command is only 1 byte long) - RFID-B1 manual 3.3
    # 01: command for "get uid and type" - RFID-B1 manual 5.4 (this command has no parameters, so we don't need to write to the command parameters register)
    read_card_data = ["01", "01", "00", "01", "00", "01"]
    # send the command to the NFC reader
    responses = send_command(read_card_data)

    # if only the command was responded to and the response is not the expected ACK, then there was an error
    if len(responses) == 1 and responses[0][0] != "00":
        # TODO log "Error Code:", responses[0][0]
        # TODO log "Error Data:", responses[0][1]
        return None
    elif len(responses) == 1:
        # if only the command was responded to and the response was an ACK, read again for the asynchronous response - RFID-B1 manual 5.4 & 4.3
        # once the command is ACKed, the NFC reader will asynchronously respond to indicate the command is complete
        responses += get_response()
    # if the command ACK and the asynchronous response were both read, then continue
    # presumably, if the command was not ACKed, then the asynchronous response was not read

    if (
        len(responses)
        < 2  # if the command ACK and the asynchronous response were not both read, then there was an error
        or responses[1][0] != "08"  # response type for asynchronous response
        or len(responses[1][1]) < 1  # asynchronous response should have 1 byte of data
        or responses[1][1][0]
        != "20"  # asynchronous response's data byte should have the 5th bit set to indicate RFID command end - RFID-B1 manual 5.6
    ):
        # TODO log print("RFID Command did not end?", responses)
        return None

    # command to read the card type
    # 02: read from rfid memory - RFID-B1 manual 5.3.3
    # 00 1E: memory address for tag type - RFID-B1 manual 3.3
    # 00 01: length of data to read (type is only 1 byte long) - RFID-B1 manual 3.3
    read_type_data = ["02", "1E", "00", "01", "00"]
    responses = send_command(read_type_data)

    # if a response was received and the response was an ACK
    if len(responses) > 0 and responses[0][0] == "00":
        # get the card type from the response
        card_type = get_type(responses[0])
        # if the card type is 06, then the card is a Mifare Classic 1k card - RFID-B1 manual 3.3.5
        if card_type == "06":
            # command to output UID of the scanned card
            # 02: read from rfid memory - RFID-B1 manual 5.3.3
            # 14: memory address for tag UID - RFID-B1 manual 3.3
            # 00 0A: length of data to read (UID saved by reader is 10 bytes long) - RFID-B1 manual 3.3
            read_uid_data = ["02", "14", "00", "0A", "00"]
            # send the command to the NFC reader - get responses back
            responses = send_command(read_uid_data)

            # if no response is received, try again up to 10 times, 0.1 seconds apart
            for _ in range(10):
                if len(responses) > 0:
                    break
                responses += get_response()
                time.sleep(0.1)

            # if a response was received and the response was an ACK
            if responses[0][0] == "00":
                # return the UID of the card
                return get_mifare_1k_uid(responses[0])
            else:
                # TODO log error
                # print("Error Code:", responses[0][0])
                # print("Error Data:", responses[0][1])
                return None
        else:
            # if the card type is not 06, then the card is not supported
            if card_type != "00":
                # TODO log unsupported card type
                pass
            # if the card type is 00, then no card was scanned
            return False
    else:
        # some error occurred in reading the card type
        # TODO log error
        return None


# put output of read_card() in a queue - needed for timeout
def read_card_queue(q):
    q.put(read_card())


def read_card_queue_timeout(time):
    """
    Call read_card() with a timeout

    time: float: the time limit in seconds

    Returns None if there was an error, or passes through the return value of read_card()
    """
    # multiprocessing is used to place a timeout on a synchronous function
    # a queue is used to pass the return value of the function back to the main process
    q = Queue()  # create a queue
    p = Process(
        target=read_card_queue, args=(q,)
    )  # create a process to run the function, passing the queue as an argument
    p.start()  # start the process
    p.join(time)  # join the process for the specified time
    # if the process does not finish in time, the main process leaves the subprocess running "asynchronously"
    # if the process finishes in time, the main process continues

    if p.is_alive():  # if the process is still running (i.e. it did not finish in time)
        p.terminate()  # terminate the process
        return None  # return None

    # if the process finished in time, get the return value from the queue and return it as uppercase
    return q.get().upper()


# clear timestamps dictionary - called whenever sheet data is refreshed
def clear_timestamps():
    global timestamps
    timestamps = {}


# close serial connection - necessary to not cause issues when we try to reopen the serial connection
# this is called when the main program exits
def close():
    ser.close()


if __name__ == "__main__":
    # test harness - check the NFC device connection and read a card
    if not check_connection():
        print("NFC device not connected")
        exit(1)
    while True:
        try:
            print(read_card())
        except KeyboardInterrupt:
            close()
            raise
