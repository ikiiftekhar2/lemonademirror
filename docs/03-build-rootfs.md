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

## 4. SSH
`openssh-server` is enabled above. For headless first contact you can allow root password login:
```sh
echo 'PermitRootLogin yes' | sudo tee rootfs/etc/ssh/sshd_config.d/10-mirror.conf
```
**Recommended once you're in:** add your SSH key to `/root/.ssh/authorized_keys` and set
`PermitRootLogin prohibit-password` / `PasswordAuthentication no`. (The mirror's sshd has no sftp
subsystem, so copy files with `scp -O` or pipe over ssh.)

## 5. Apply the LemonadeMirror overlay
Copy the repo's overlay (services, ALSA config, camera hub + helper scripts) on top of the rootfs:
```sh
sudo cp -a /path/to/lemonademirror/rootfs/overlay/* rootfs/
sudo chroot rootfs systemctl enable camhub.service screen-off.service
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

Next: [flash and make it persistent](04-flash-and-persist.md).
