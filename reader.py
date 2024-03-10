import fake_nfc as nfc
# import reader_nfc as nfc
import sheet
from multiprocessing import Process, Queue
from time import sleep

# def f(time):
#     sleep(time)


# def run_with_limited_time(func, args, kwargs, time):
#     """Runs a function with time limit

#     :param func: The function to run
#     :param args: The functions args, given as tuple
#     :param kwargs: The functions keywords, given as dict
#     :param time: The time limit in seconds
#     :return: True if the function ended successfully. False if it was terminated.
#     """
#     q = Queue()
#     p = Process(target=func, args=args + [q], kwargs=kwargs)
#     p.start()
#     p.join(time)
#     if p.is_alive():
#         p.terminate()
#         return False

#     return True


# if __name__ == '__main__':
#     print run_with_limited_time(f, (1.5, ), {}, 2.5) # True
#     print run_with_limited_time(f, (3.5, ), {}, 2.5) # False

if __name__ == "__main__":
    sheet.get_sheet_data(limited=True)
    try:
        while True:
            print("Hold a tag near the reader")
            # print(nfc.read_card())
            card_id = nfc.read_card_queue_timeout(10)
            # card_id = "63B104FF"
            print(card_id)
            if card_id:
                response = sheet.scan_uid(card_id)
                if not response:
                    print("error")
                    # card not in database or some other error
                    pass
                else:
                    color, timeout = response
                    print(color, timeout)
    except KeyboardInterrupt:
        # nfc.close()
        raise
