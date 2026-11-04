#!/bin/sh
# Burn the LemonadeMirror image. Get U-Boot, back up your eMMC, run `ums 0 mmc 2`, then:
#   sudo ./flash-mirror.sh /dev/sdX        (Linux)
#   sudo ./flash-mirror.sh /dev/rdisk4     (macOS)
# Find the disk with `lsblk` or `diskutil list`. The tool refuses anything but a Mirror V1.1.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
exec python3 -I "$HERE/flash-mirror.py" "$@"
