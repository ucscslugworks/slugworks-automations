from multiprocessing import Process, Queue


def read_card():
    return input("Enter card ID: ")


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

    r = q.get()
    return r if not r else r.upper()


def close():
    pass
