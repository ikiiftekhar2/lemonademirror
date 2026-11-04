#!/usr/bin/env python3
"""Flash a LemonadeMirror image onto a Lululemon Mirror V1.1 exposed by `ums 0 mmc 2`.

Writes ONLY the boot_b and userdata partitions. The bootloader, Android and the
partition table stay untouched. Refuses any disk that doesn't look like this board.
Standard library only; runs on Linux and macOS. Use flash-mirror.sh to start it.
"""
import argparse
import binascii
import getpass
import hashlib
import lzma
import os
import platform
import struct
import subprocess
import sys
import time
import uuid

SECTOR = 512
CHUNK = 4 * 1024 * 1024
BOOT_SLOT = b"@@MIRROR_BOOTSCR_SLOT@@"
CONFIG_SLOT = b"@@MIRROR_CONFIG_SLOT@@"
BOOT_SLOT_SIZE = 2048
CONFIG_SLOT_SIZE = 4096
# As the GPT describes it: the reference table covers 13.0 GiB of a 14.6 GiB chip.
EXPECTED_DISK_GIB = (12.5, 15.5)
# Partition name -> (first LBA, sector count) on the reference V1.1 unit.
EXPECTED = {"boot_a": (0x8000, 0x20000), "boot_b": (0x28000, 0x20000), "super": (0x4c000, 0xe00000)}
BOOTCMD = "mmc dev 2; fatload mmc 2:4 0x40800000 /boot.scr; source 0x40800000"
BOOT_CMD_TEMPLATE = """setenv kernel_addr 0x40480000
setenv fdt_addr 0x44480000
setenv bootargs "console=ttymxc1,115200 root=PARTUUID=%s rw rootwait fbcon=rotate:3"
mmc dev 2
fatload mmc 2:4 ${kernel_addr} /Image
fatload mmc 2:4 ${fdt_addr} /imx8mm-mirror.dtb
booti ${kernel_addr} - ${fdt_addr}
"""


def die(msg):
    sys.exit("\nSTOPPED: " + msg + "\nNothing further was written.")


def make_boot_scr(partuuid, stamp=None):
    """A U-Boot legacy script image, the same bytes `mkimage -T script` produces."""
    script = (BOOT_CMD_TEMPLATE % partuuid).encode()
    data = struct.pack(">II", len(script), 0) + script
    stamp = int(time.time()) if stamp is None else stamp
    header = lambda crc: struct.pack(
        ">IIIIIIIBBBB32s", 0x27051956, crc, stamp, len(data), 0x40800000, 0x40800000,
        binascii.crc32(data), 5, 22, 6, 0, b"LemonadeMirror boot")
    image = header(binascii.crc32(header(0))) + data
    if len(image) > BOOT_SLOT_SIZE:
        die("boot script is too large")
    return image


def make_config(answers):
    lines = ["# Read once on first boot, then wiped."]
    lines += ["%s=%s" % item for item in answers.items()]
    text = "\n".join(lines) + "\n#END\n"
    data = text.encode()
    if len(data) > CONFIG_SLOT_SIZE:
        die("settings are too long")
    return data


def patch_slot(image, marker, size, content):
    pos = image.find(marker)
    if pos < 0 or image.find(marker, pos + 1) >= 0:
        die("the boot image is damaged (slot %s)" % marker.decode())
    image[pos:pos + size] = content.ljust(size, b"\n")


def read_gpt(disk):
    disk.seek(SECTOR)
    header = disk.read(SECTOR)
    if header[:8] != b"EFI PART":
        die("no GPT on this disk, so it isn't an exposed Mirror eMMC")
    hsize = struct.unpack_from("<I", header, 12)[0]
    check = bytearray(header[:hsize])
    check[16:20] = b"\0\0\0\0"
    if binascii.crc32(bytes(check)) != struct.unpack_from("<I", header, 16)[0]:
        die("the GPT header checksum is wrong")
    lba, count, size = struct.unpack_from("<QII", header, 72)
    disk.seek(lba * SECTOR)
    table = disk.read(count * size)
    if binascii.crc32(table) != struct.unpack_from("<I", header, 88)[0]:
        die("the GPT table checksum is wrong")
    parts = {}
    for i in range(count):
        entry = table[i * size:(i + 1) * size]
        if entry[:16] == b"\0" * 16:
            continue
        first, last = struct.unpack_from("<QQ", entry, 32)
        name = entry[56:128].decode("utf-16-le").split("\0")[0]
        parts[name] = (first, last - first + 1, str(uuid.UUID(bytes_le=entry[16:32])))
    return parts


def read_sector(disk, offset):
    """Whole sectors only: macOS raw disks reject anything smaller."""
    disk.seek(offset)
    return disk.read(4096)


def gpt_disk_bytes(disk):
    """The disk's size according to its GPT, which works on any OS and device type."""
    disk.seek(SECTOR)
    return (struct.unpack_from("<Q", disk.read(SECTOR), 32)[0] + 1) * SECTOR


def check_board(path, disk, need_root_bytes):
    parts = read_gpt(disk)
    gib = gpt_disk_bytes(disk) / 1024 ** 3
    if not EXPECTED_DISK_GIB[0] <= gib <= EXPECTED_DISK_GIB[1]:
        die("%s has a %.1f GiB partition table; a Mirror V1.1 has 13.0 GiB" % (path, gib))
    for name, (first, count) in EXPECTED.items():
        if name not in parts or parts[name][:2] != (first, count):
            die("partition %s isn't where a Mirror V1.1 keeps it. This image is only for that board." % name)
    if "userdata" not in parts:
        die("no userdata partition")
    if parts["userdata"][1] * SECTOR < need_root_bytes:
        die("userdata is too small for the image")
    if read_sector(disk, parts["super"][0] * SECTOR + 4096 * 3)[:4] != b"0PLA":
        die("Android's super partition is missing or damaged, and first boot needs its firmware")
    if read_sector(disk, parts["boot_a"][0] * SECTOR)[:8] != b"ANDROID!":
        die("Android's boot_a partition is missing or damaged, and first boot needs its firmware")
    return parts


def unmount(path):
    if platform.system() == "Darwin":
        subprocess.run(["diskutil", "unmountDisk", path.replace("/dev/rdisk", "/dev/disk")], check=True)
        return
    with open("/proc/mounts") as f:
        if any(line.startswith(path) for line in f):
            die("%s has mounted partitions. Unmount them first." % path)


def write_region(disk, offset, chunks, total, label):
    disk.seek(offset)
    digest = hashlib.sha256()
    written = 0
    for chunk in chunks:
        digest.update(chunk)
        if len(chunk) % SECTOR:
            chunk = chunk + b"\0" * (SECTOR - len(chunk) % SECTOR)
        disk.write(chunk)
        written += len(chunk)
        print("\r  %s: %d of %d MiB" % (label, written >> 20, total >> 20), end="", flush=True)
    disk.flush()
    os.fsync(disk.fileno())
    print()
    return digest.hexdigest(), written


def verify_region(disk, offset, length, want, label):
    disk.seek(offset)
    digest = hashlib.sha256()
    left = length
    while left:
        chunk = disk.read(min(CHUNK, left))
        if not chunk:
            die("read-back of %s ended early" % label)
        digest.update(chunk)
        left -= len(chunk)
        print("\r  verifying %s: %d MiB left   " % (label, left >> 20), end="", flush=True)
    print()
    if digest.hexdigest() != want:
        die("%s doesn't match what was written. Don't reboot; run this tool again." % label)


def rootfs_chunks(path):
    opener = lzma.open if path.endswith(".xz") else open
    with opener(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                return
            yield chunk


def rootfs_size(path):
    if not path.endswith(".xz"):
        return os.path.getsize(path)
    with lzma.open(path, "rb") as f:
        return f.seek(0, os.SEEK_END)


def ask_settings(args):
    if args.settings:
        answers = {}
        with open(args.settings, encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    key, value = line.rstrip("\n").split("=", 1)
                    answers[key] = value
        return answers
    print("\nSettings for your mirror (stored only until its first boot):")
    ssid = input("  Wi-Fi name (SSID): ").strip()
    if not ssid:
        die("a Wi-Fi name is required, because the mirror has no other way onto your network")
    wifi = getpass.getpass("  Wi-Fi password (blank for an open network): ")
    if wifi and not 8 <= len(wifi) <= 63:
        die("a WPA password is 8 to 63 characters")
    while True:
        password = getpass.getpass("  New password for the 'mirror' login: ")
        if len(password) < 8:
            print("  Use at least 8 characters.")
        elif password != getpass.getpass("  Same password again: "):
            print("  They don't match.")
        else:
            break
    hostname = input("  Hostname [mirror]: ").strip() or "mirror"
    timezone = input("  Time zone, e.g. America/Toronto [UTC]: ").strip()
    key_path = input("  SSH public key file (blank to log in with the password): ").strip()
    key = ""
    if key_path:
        with open(os.path.expanduser(key_path), encoding="utf-8") as f:
            key = f.read().strip()
    return {"WIFI_SSID": ssid, "WIFI_PASSWORD": wifi, "PASSWORD": password,
            "HOSTNAME": hostname, "TIMEZONE": timezone, "SSH_KEY": key}


def backup_boot_b(disk, parts, folder):
    first, count, _ = parts["boot_b"]
    path = os.path.join(folder, "backup-boot_b-%s.img" % time.strftime("%Y%m%d-%H%M%S"))
    disk.seek(first * SECTOR)
    with open(path, "wb") as out:
        left = count * SECTOR
        while left:
            chunk = disk.read(min(CHUNK, left))
            if not chunk:
                die("couldn't read boot_b for its backup")
            out.write(chunk)
            left -= len(chunk)
    print("  saved %s" % path)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("device", help="the Mirror's disk, e.g. /dev/sdX or /dev/rdisk4 (macOS)")
    ap.add_argument("--rootfs", default=os.path.join(here, "mirror-rootfs.img.xz"))
    ap.add_argument("--boot", default=os.path.join(here, "mirror-boot.img"))
    ap.add_argument("--settings", help="read the settings from a KEY=value file, not prompts")
    ap.add_argument("--yes-i-have-a-backup", action="store_true", help="skip the typed confirmation")
    args = ap.parse_args()

    for path in (args.rootfs, args.boot):
        if not os.path.exists(path):
            die("%s not found" % path)
    print("Reading the image...")
    root_bytes = rootfs_size(args.rootfs)
    with open(args.boot, "rb") as f:
        boot = bytearray(f.read())

    if args.device.startswith("/dev/"):
        unmount(args.device)
    with open(args.device, "r+b", buffering=0) as disk:
        parts = check_board(args.device, disk, root_bytes)
        print("\nThis looks like a Mirror V1.1 eMMC: %s" % args.device)
        for name in ("boot_b", "userdata"):
            print("  will overwrite %-9s %5d MiB" % (name, (parts[name][1] * SECTOR) >> 20))
        print("  left alone: bootloader, boot_a, super (Android), partition table")
        if not args.yes_i_have_a_backup:
            print("\nThis ERASES boot_b and userdata. Back up your whole eMMC first (see docs).")
            if input("Type I HAVE A BACKUP to continue: ") != "I HAVE A BACKUP":
                die("not confirmed")
        answers = ask_settings(args)

        patch_slot(boot, BOOT_SLOT, BOOT_SLOT_SIZE, make_boot_scr(parts["userdata"][2]))
        patch_slot(boot, CONFIG_SLOT, CONFIG_SLOT_SIZE, make_config(answers))
        if len(boot) > parts["boot_b"][1] * SECTOR:
            die("the boot image is larger than boot_b")

        print("\nBacking up the current boot_b...")
        backup_boot_b(disk, parts, os.path.dirname(os.path.abspath(args.rootfs)))

        print("\nWriting...")
        root_off = parts["userdata"][0] * SECTOR
        root_hash, _ = write_region(disk, root_off, rootfs_chunks(args.rootfs), root_bytes, "rootfs")
        verify_region(disk, root_off, root_bytes, root_hash, "rootfs")
        boot_off = parts["boot_b"][0] * SECTOR
        boot_hash = hashlib.sha256(bytes(boot)).hexdigest()
        write_region(disk, boot_off, [bytes(boot)], len(boot), "boot")
        verify_region(disk, boot_off, len(boot), boot_hash, "boot")

    print("""
Flash complete. Last steps, on the U-Boot serial console:
  1. Press Ctrl+C to leave USB mode.
  2. Run these two commands, one at a time:
       setenv bootcmd '%s'
       saveenv
  3. Cut power, then plug it back in.

First boot takes a few minutes: the mirror extracts its firmware, sets itself up and
restarts once. The screen stays dark. Then log in with:
  ssh mirror@%s      (or find its IP address in your router)
  sudo mirror-hwcheck
""" % (BOOTCMD, answers.get("HOSTNAME") or "mirror"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
