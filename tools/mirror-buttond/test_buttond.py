#!/usr/bin/env python3
"""Hardware-free test: feed fake input events through a FIFO, check socket output."""
import os, socket, struct, subprocess, sys, tempfile, time

KEY_PROG1 = 148
OTHER_KEY = 68


def key(fifo, value, code=KEY_PROG1):
    os.write(fifo, struct.pack("<qqHHi", 0, 0, 1, code, value))


def collect(sock, seconds):
    sock.settimeout(seconds)
    data = b""
    end = time.time() + seconds
    while time.time() < end:
        try:
            sock.settimeout(max(0.01, end - time.time()))
            chunk = sock.recv(256)
            if not chunk:
                break
            data += chunk
        except socket.timeout:
            break
    return data.decode().split()


def tap_once(f):
    key(f, 1); time.sleep(0.05); key(f, 0)


def case_tap(f):
    tap_once(f)


def case_double(f):
    tap_once(f); time.sleep(0.05); tap_once(f)


def case_hold(f):
    key(f, 1); time.sleep(0.45); key(f, 0)


def case_two_taps_apart(f):
    tap_once(f); time.sleep(0.25); tap_once(f)


def case_second_press_held(f):
    tap_once(f); time.sleep(0.05); key(f, 1); time.sleep(0.45); key(f, 0)


def case_other_key_ignored(f):
    key(f, 1, OTHER_KEY); key(f, 0, OTHER_KEY)


CASES = [
    ("tap", case_tap, ["press", "release", "tap"]),
    ("double", case_double, ["press", "release", "press", "release", "double"]),
    ("hold", case_hold, ["press", "hold", "release"]),
    ("two separate taps", case_two_taps_apart,
     ["press", "release", "tap", "press", "release", "tap"]),
    ("second press held", case_second_press_held,
     ["press", "release", "press", "hold", "release"]),
    ("other key ignored", case_other_key_ignored, []),
]


def main(binary):
    tmp = tempfile.mkdtemp()
    fifo_path, sock_path = os.path.join(tmp, "in"), os.path.join(tmp, "s")
    os.mkfifo(fifo_path)
    # hold 300 ms, double window 150 ms: same logic as the defaults, faster test
    daemon = subprocess.Popen([binary, "-i", fifo_path, "-s", sock_path, "-H", "300", "-d", "150"])
    fifo = os.open(fifo_path, os.O_WRONLY)
    for _ in range(50):
        if os.path.exists(sock_path):
            break
        time.sleep(0.02)

    clients = [socket.socket(socket.AF_UNIX) for _ in range(2)]
    for c in clients:
        c.connect(sock_path)
    time.sleep(0.05)

    failed = 0
    for name, fn, want in CASES:
        fn(fifo)
        got = [collect(clients[0], 0.5), collect(clients[1], 0.05)]
        ok = got[0] == want and got[1] == want
        failed += not ok
        print(("PASS" if ok else "FAIL"), name, got[0], "" if ok else "want %s second=%s" % (want, got[1]))

    # a client that disconnects must not hurt the daemon or other clients
    clients[1].close()
    case_tap(fifo)
    got = collect(clients[0], 0.5)
    ok = got == ["press", "release", "tap"] and daemon.poll() is None
    failed += not ok
    print(("PASS" if ok else "FAIL"), "client disconnect", got)

    daemon.terminate()
    daemon.wait()
    print("FAILED %d" % failed if failed else "ALL PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
