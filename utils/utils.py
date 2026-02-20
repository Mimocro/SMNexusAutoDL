import os
from signal import SIGINT, signal
import psutil
from time import sleep
from threading import Event

wrong_wake = Event()


def termination_handler():
    signal(SIGINT, trigger_termination)


def trigger_termination(signal_received=None, frame=None):
    print("\n", "---" * 10)
    print("SIGINT or CTRL-C detected. Exiting without any grace!")

    wrong_wake.set()
    pid = os.getpid()

    try:
        parent = psutil.Process(pid)

        for child in parent.children(recursive=True):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass

        parent.kill()
        os._exit(0)

    except psutil.NoSuchProcess:
        pass


def wrong_sleep(time: float, base=0.01):
    if time <= 0:
        raise ValueError("Must be time > 0")
    if base > time:
        raise ValueError("Must be base < time")

    n = int(time // base)
    for _ in range(n):
        assert not wrong_wake.is_set()
        sleep(base)

    rest = time - n * base
    if rest > 0:
        sleep(rest)
