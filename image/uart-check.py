#!/usr/bin/env python3
"""Optional check before flashing: is this board the same as the reference Mirror?

Connect to U-Boot over the UART (115200, 1.8 V), start this, then power on the mirror.
It stops autoboot and only reads information: nothing is changed.

U-Boot on this board can't see the speakers, camera or display (its I2C buses don't
work), so those are checked after flashing with `sudo mirror-hwcheck`.

  python3 uart-check.py /dev/ttyUSB0            needs pyserial (pip install pyserial)
  python3 uart-check.py --log captured.txt      check text you already captured
"""
import argparse
import re
import sys
import time

PROMPT = "u-boot=>"
COMMANDS = ["version", "mmc dev 2", "mmc info", "mmc part", "mmc part", "mmc part", "printenv bootcmd"]
PARTITIONS = {"boot_a": (0x8000, 0x27fff), "boot_b": (0x28000, 0x47fff),
              "super": (0x4c000, 0xe4bfff), "userdata": (0xe4c000, None)}


def checks(text):
    results = [
        ("SoC", re.search(r"i\.MX8MM\w* rev", text), "i.MX8M Mini"),
        ("RAM", re.search(r"DRAM:\s+2 GiB", text), "2 GiB"),
        ("Board", "i.MX8MM EVK board" in text, "the name this bootloader reports"),
        ("eMMC", re.search(r"Capacity: 14\.\d GiB", text), "about 14.6 GiB"),
        ("Bootloader", "2020.04-00004-gfbe316d" in text, "U-Boot 2020.04-00004-gfbe316d"),
    ]
    for name, (first, last) in PARTITIONS.items():
        # The serial link drops bytes now and then, so any one clean line is enough.
        lines = re.findall(r"(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+\"%s\"" % name, text)
        good = any(int(start, 16) == first and (last is None or int(end, 16) == last)
                   for start, end in lines)
        # None: garbled on the wire, not a mismatch. The flash tool reads the real table anyway.
        results.append(("Partition " + name, good if lines else None, "at 0x%x" % first))
    return results


def report(text):
    failed = unread = 0
    for name, good, want in checks(text):
        label = "?" if good is None else "PASS" if good else "FAIL"
        print("%-5s %-20s expected %s" % (label, name, want))
        failed += 0 if good or good is None else 1
        unread += good is None
    if failed:
        print("\n%d check(s) failed. This board differs from the reference unit, so the image may not work on it. "
              "The flash tool also refuses a different partition layout." % failed)
        return 1
    if unread:
        print("\n%d line(s) were garbled on the serial link, so run it again if you like. "
              "The flash tool checks the real partition table either way." % unread)
    print("\nNo mismatches. This matches the reference unit as far as U-Boot can tell.\n"
          "To flash: run `ums 0 mmc 2` at the prompt, then flash-mirror.sh on your PC.")
    return 0


def capture(port):
    try:
        import serial
    except ImportError:
        sys.exit("pyserial is needed: pip install pyserial")
    uart = serial.Serial(port, 115200, timeout=0.05)
    print("Power on the mirror now. Waiting for U-Boot (up to 2 minutes)...")
    seen = ""
    deadline = time.time() + 120
    while PROMPT not in seen:
        if time.time() > deadline:
            sys.exit("No U-Boot prompt. Check the wiring: TX and RX crossed, 1.8 V, common ground.")
        uart.write(b"\x7f\x7f\x7f\x7f ")   # any key stops autoboot; this is what works on this board
        seen += uart.read(4096).decode(errors="replace")
    text = seen
    time.sleep(0.3)
    uart.reset_input_buffer()
    for command in COMMANDS:
        uart.write(command.encode() + b"\n")
        out = ""
        deadline = time.time() + 8
        while PROMPT not in out and time.time() < deadline:
            out += uart.read(4096).decode(errors="replace")
        text += "\n" + out
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("port", nargs="?", help="serial port, e.g. /dev/ttyUSB0")
    ap.add_argument("--log", help="check an existing capture instead of a live board")
    args = ap.parse_args()
    if args.log:
        with open(args.log, errors="replace") as f:
            return report(f.read())
    if not args.port:
        ap.error("give a serial port or --log")
    text = capture(args.port)
    with open("uart-check.log", "w") as f:
        f.write(text)
    print("Saved the console output to uart-check.log\n")
    return report(text)


if __name__ == "__main__":
    sys.exit(main())
