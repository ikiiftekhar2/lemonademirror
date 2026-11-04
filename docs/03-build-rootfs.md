# 3. Build a Debian rootfs with your WiFi + SSH baked in

Goal: a Debian arm64 rootfs that comes up headless. Preseeding the WiFi credentials and SSH config
into the image means the mirror joins the network and accepts SSH on first boot — no keyboard or
monitor, and every subsequent step is done over the network. The repo provides config templates;
populate them with your network and credentials at build time.

## 1. Bootstrap Debian (arm64)
On a Linux PC (uses `qemu-user-static` for the cross-arch second stage):
```sh
sudo apt install debootstrap qemu-user-static
sudo debootstrap --arch=arm64 --foreign bookworm rootfs \
  http://deb.debian.org/debian
sudo cp /usr/bin/qemu-aarch64-static rootfs/usr/bin/
sudo chroot rootfs /debootstrap/debootstrap --second-stage
```

## 2. Base setup (inside the chroot)
```sh
sudo chroot rootfs /bin/bash
  apt install -y network-manager openssh-server alsa-utils i2c-tools v4l-utils ffmpeg systemd-timesyncd
  systemctl enable NetworkManager ssh systemd-timesyncd
  echo mirror > /etc/hostname
  passwd root            # set a root password
  exit
```
Install the kernel modules you built ([step 2](02-build-kernel.md)) into
`rootfs/lib/modules/6.18.60-dirty/`.

## 3. WiFi (fill in the template)
Populate the template with your network:
```sh
sudo cp /path/to/lemonademirror/rootfs/templates/wifi.nmconnection.template \
        rootfs/etc/NetworkManager/system-connections/mirror-wifi.nmconnection
sudoedit rootfs/etc/NetworkManager/system-connections/mirror-wifi.nmconnection   # set SSID + PSK
sudo chmod 600 rootfs/etc/NetworkManager/system-connections/mirror-wifi.nmconnection
```

## 4. SSH access (do this the safe way)

This device sits on your network, so **don't leave root-with-a-password reachable over SSH.** The
recommended setup is a normal sudo user authenticated by an SSH **key**, with root login and password
auth turned off. Preseed it so it's safe from the very first boot:

```sh
sudo chroot rootfs /bin/bash
  adduser mirror                       # a regular user (set a password)
  usermod -aG sudo mirror
  install -d -m700 -o mirror -g mirror /home/mirror/.ssh
  # paste YOUR public key:
  echo 'ssh-ed25519 AAAA...you' > /home/mirror/.ssh/authorized_keys
  chmod 600 /home/mirror/.ssh/authorized_keys
  chown mirror:mirror /home/mirror/.ssh/authorized_keys
  cat > /etc/ssh/sshd_config.d/10-mirror.conf <<'CONF'
PermitRootLogin no
PasswordAuthentication no
CONF
  exit
```
Now you log in as `mirror` with your key and `sudo` for root. (The mirror's sshd has no sftp
subsystem, so copy files with `scp -O` or pipe over ssh.)

> **If you must bootstrap with a password first** (no key handy, can't reach the console): set
> `PasswordAuthentication yes` *temporarily*, use a **strong, unique** password (never a default from
> any guide), get your key installed, then switch both lines back to the safe values above. Root
> password login over SSH is a bring-up crutch, not a resting state — the reference unit's "root +
> password" setup was bench convenience, not a recommendation.

## 5. Apply the LemonadeMirror overlay
Copy the repo's overlay (services, ALSA config, camera hub + helper scripts) on top of the rootfs:
```sh
sudo cp -a /path/to/lemonademirror/rootfs/overlay/* rootfs/
sudo chroot rootfs systemctl enable camhub.service screen-off.service mirror-buttond.service
# screen-off races with this restore service and can lose, lighting the screen at boot
sudo chroot rootfs systemctl mask systemd-backlight@backlight:backlight.service
# the reboot fix (see drivers/reboot.md) needs the kernel build's module in place:
# rootfs/overlay/usr/local/lib/mirror-reboot/mirror_reset_now.ko is built for vermagic 6.18.60-dirty
# the Bluetooth name
sudo sed -i -E '0,/^#?Name *=.*/s//Name = Lemonade Mirror/' rootfs/etc/bluetooth/main.conf
```
Add the extracted vendor firmware blobs ([step 5](05-extract-vendor-blobs.md)) under
`rootfs/lib/firmware/`. Optionally install OpenCV for gesture/ML work (a headless pip venv keeps it
small — see the [developer guide](developer-guide.md)).

## 6. Package it
Make an ext4 image from the tree (size it for your partition):
```sh
sudo mkfs.ext4 -d rootfs mirror-rootfs.img 5G
```
This image goes onto the eMMC in the next step. **Note the partition's PARTUUID after you write it** —
you'll put it in the boot script.

## After first boot — change your credentials
The WiFi PSK and root password are **baked into the rootfs image** at build time. If you reuse a
prebuilt/shared image (or just want to rotate them), change them once you're in over SSH:
```sh
nmcli connection modify mirror-wifi wifi-sec.psk 'NEW_WIFI_PASSWORD'   # or set a new SSID/connection
passwd root                                                           # new root password
# optional hardening: install your SSH key, then disable password login
#   sshd_config: PasswordAuthentication no  /  PermitRootLogin prohibit-password
```
**Never publish or share a rootfs image with your real WiFi PSK or password in it** — that's exactly
why this repo ships a template, not an image.

Next: [flash and make it persistent](04-flash-and-persist.md).
