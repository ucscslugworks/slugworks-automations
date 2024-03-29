import random
import string
import time
from multiprocessing import Process, Queue


def read_card():
    # # delay = random.randint(0, 20)
    # # print('delay', delay)
    # # time.sleep(delay)
    # if (random.random() > 2/3):
    #     return "".join(
    #         random.choice(string.ascii_lowercase + string.digits) for _ in range(8)
    #     )
    # elif (random.random() > 1/3):
    #     return random.choice(["63B104FF", "73B104FF", "83B104FF"])
    # else:
    #     return random.choice([None, False])
    return "20646297"


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
    pass
