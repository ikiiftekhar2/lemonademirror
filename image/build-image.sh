#!/usr/bin/env bash
# Build a clean, flashable LemonadeMirror image from scratch on a Debian/Ubuntu PC.
# Output in OUT/: mirror-rootfs.img.xz, mirror-boot.img, SHA256SUMS.
#
# Contains no Wi-Fi details, passwords, SSH keys or vendor firmware. Those are added
# at flash time (flash-mirror.sh) or extracted by the mirror itself on first boot.
#
# Needs root, debootstrap, qemu-user-static, dosfstools, e2fsprogs, xz-utils, internet.
# Usage: sudo image/build-image.sh [work-dir]   (default: ./image-build)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(realpath -m "${1:-image-build}")"
ROOT="$WORK/rootfs"
OUT="$WORK/dist"
KVER=6.18.60-dirty
ROOT_MIB=3500
BOOT_MIB=64
MIRROR=http://deb.debian.org/debian

[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
for tool in debootstrap qemu-aarch64-static mkfs.ext4 mkfs.vfat xz python3; do
    command -v "$tool" >/dev/null || { echo "missing tool: $tool"; exit 1; }
done

cleanup() {
    for m in dev/pts dev proc sys; do
        mountpoint -q "$ROOT/$m" && umount -l "$ROOT/$m"
    done
    mountpoint -q "$WORK/bootmnt" && umount "$WORK/bootmnt"
    return 0
}
trap cleanup EXIT

in_root() { chroot "$ROOT" /usr/bin/env -i HOME=/root PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    DEBIAN_FRONTEND=noninteractive LC_ALL=C "$@"; }

echo "== 1/7 Debian base"
rm -rf "$WORK"; mkdir -p "$ROOT" "$OUT"
debootstrap --arch=arm64 --foreign --variant=minbase trixie "$ROOT" "$MIRROR"
install -m 755 "$(command -v qemu-aarch64-static)" "$ROOT/usr/bin/qemu-aarch64-static"
chroot "$ROOT" /debootstrap/debootstrap --second-stage
mount -t proc proc "$ROOT/proc"; mount -t sysfs sys "$ROOT/sys"
mount --bind /dev "$ROOT/dev"; mount --bind /dev/pts "$ROOT/dev/pts"
cp /etc/resolv.conf "$ROOT/etc/resolv.conf"
printf '#!/bin/sh\nexit 101\n' > "$ROOT/usr/sbin/policy-rc.d"; chmod 755 "$ROOT/usr/sbin/policy-rc.d"

echo "== 2/7 packages"
cat > "$ROOT/etc/apt/sources.list" <<LIST
deb $MIRROR trixie main non-free-firmware
deb $MIRROR trixie-updates main non-free-firmware
deb http://security.debian.org/debian-security trixie-security main non-free-firmware
LIST
in_root apt-get update
# Every package name from the reference unit, skipping any Debian no longer carries.
in_root apt-cache pkgnames > "$WORK/available.txt"
grep -Fxf "$WORK/available.txt" "$REPO/image/packages.txt" > "$WORK/install.txt"
in_root apt-get install -y --no-install-recommends $(cat "$WORK/install.txt")

echo "== 3/7 kernel modules"
mkdir -p "$ROOT/lib/modules"
tar xzf "$REPO/prebuilt/modules-$KVER.tar.gz" -C "$ROOT/lib/modules"
rm -f "$ROOT/lib/modules/$KVER/build" "$ROOT/lib/modules/$KVER/source"
in_root depmod -a "$KVER"

echo "== 4/7 LemonadeMirror files and services"
cp -a "$REPO/rootfs/overlay/." "$ROOT/"
chmod 755 "$ROOT"/usr/local/sbin/* "$ROOT"/usr/local/bin/*
cat > "$ROOT/etc/fstab" <<FSTAB
LABEL=MIRRORROOT  /     ext4   defaults,noatime  0 1
tmpfs             /tmp  tmpfs  defaults,nosuid,nodev,mode=1777  0 0
FSTAB
echo mirror > "$ROOT/etc/hostname"
printf '127.0.0.1\tlocalhost\n127.0.1.1\tmirror\n::1\t\tlocalhost ip6-localhost ip6-loopback\n' > "$ROOT/etc/hosts"
sed -i -E '0,/^#?Name *=.*/s//Name = Lemonade Mirror/' "$ROOT/etc/bluetooth/main.conf"
mkdir -p "$ROOT/etc/ssh/sshd_config.d"
echo 'PermitRootLogin no' > "$ROOT/etc/ssh/sshd_config.d/10-mirror.conf"
in_root useradd -m -s /bin/bash -G sudo,input,video,audio,render mirror
in_root passwd -l mirror
in_root passwd -l root
in_root systemctl enable mirror-firstboot.service camhub.service screen-off.service \
    mirror-buttond.service bluetooth.service ssh.service NetworkManager.service \
    systemd-timesyncd.service serial-getty@ttymxc1.service
in_root systemctl mask systemd-backlight@backlight:backlight.service getty@ttymxc1.service

echo "== 5/7 OpenCV environment"
in_root python3 -m venv /opt/mirror-cv
in_root /opt/mirror-cv/bin/pip install --no-cache-dir numpy==2.5.4 opencv-python-headless==5.0.0.93

echo "== 6/7 scrub"
in_root apt-get clean
rm -rf "$ROOT"/var/lib/apt/lists/* "$ROOT"/var/log/* "$ROOT"/tmp/* "$ROOT"/var/tmp/* \
    "$ROOT"/root/.cache "$ROOT"/root/.bash_history "$ROOT"/usr/sbin/policy-rc.d \
    "$ROOT"/etc/ssh/ssh_host_* "$ROOT"/usr/bin/qemu-aarch64-static "$ROOT"/debootstrap
find "$ROOT/opt/mirror-cv" -name __pycache__ -type d -prune -exec rm -rf {} +
: > "$ROOT/etc/machine-id"
rm -f "$ROOT/var/lib/dbus/machine-id" "$ROOT/etc/resolv.conf"
ln -s /run/NetworkManager/resolv.conf "$ROOT/etc/resolv.conf"
cleanup

echo "== 7/7 images"
truncate -s ${ROOT_MIB}M "$OUT/mirror-rootfs.img"
mkfs.ext4 -q -F -L MIRRORROOT -b 4096 -d "$ROOT" "$OUT/mirror-rootfs.img"
e2fsck -fn "$OUT/mirror-rootfs.img"

truncate -s ${BOOT_MIB}M "$OUT/mirror-boot.img"
mkfs.vfat -F 16 -n MIRRORBOOT "$OUT/mirror-boot.img" >/dev/null
mkdir -p "$WORK/bootmnt"
mount -o loop "$OUT/mirror-boot.img" "$WORK/bootmnt"
# Reserved slots: the flash tool overwrites these bytes in place with the unit's values.
python3 -c "import sys;sys.stdout.buffer.write(b'@@MIRROR_BOOTSCR_SLOT@@'.ljust(2048,b'\n'))" > "$WORK/bootmnt/boot.scr"
python3 -c "import sys;sys.stdout.buffer.write(b'@@MIRROR_CONFIG_SLOT@@'.ljust(4096,b'\n'))" > "$WORK/bootmnt/mirror-config.txt"
cp "$REPO/prebuilt/imx8mm-mirror.dtb" "$REPO/prebuilt/Image" "$WORK/bootmnt/"
umount "$WORK/bootmnt"

( cd "$OUT"; sha256sum mirror-rootfs.img mirror-boot.img > SHA256SUMS.raw
  xz -T0 -6 mirror-rootfs.img
  sha256sum mirror-rootfs.img.xz mirror-boot.img > SHA256SUMS.files )
du -h "$OUT"/*
echo "image ready: $OUT"
