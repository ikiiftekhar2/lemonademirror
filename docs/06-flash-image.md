# Flash the ready-made image

An optional shortcut. The main thing this project offers is [the kernel package](../README.md#the-kernel-package); this script is a convenience on top of it. It burns a ready-made Debian image that includes that kernel, so you'll have the display, speakers, mic, camera, Wi-Fi, Bluetooth and bottom button set up, and `reboot` working over SSH.

**This guide starts once you can reach the `u-boot=>` prompt.** To get there on a locked unit, follow **[gouda-percha's guide](https://failedattempts.neocities.org/)**. None of this project would be possible without that work, so a huge thank you to gouda-percha for figuring it out and sharing it. There's more detail in [Get a U-Boot prompt](01-get-uboot.md).

> ✅ **Tested on real hardware:** on 7 November 2026 the flash tool burned this image onto a second Mirror V1.1 (not the reference unit) from macOS. It booted, passed `mirror-hwcheck` 20 of 20, and the picture, speakers and mic checked out by eye and ear. See [What has been tested](#what-has-been-tested). That's one real burn so far, so still do step 2 first, and please [report how it goes](https://github.com/ikiiftekhar2/lemonademirror/issues).

## Before you start

**This is only for a Lululemon Mirror V1.1:** i.MX8M Mini, 2 GiB RAM, 14.6 GiB eMMC. The flash tool checks the partition layout and refuses anything else.

**You need:**
- A 1.8 V USB-UART adapter on the A53 UART, 115200 8N1. ⚠️ Don't connect 3.3 V or 5 V to the UART pads.
- A micro-USB data cable from your PC to the micro-USB port on the mirror's I/O board.
- A Linux or macOS PC with Python 3, and about 16 GiB free for the backup.

**What gets erased:** the `boot_b` and `userdata` partitions, including your Android data. So the mirror won't run Lululemon's software until you restore your backup.

**What stays:** the bootloader, `boot_a`, `super` (Android's system) and the partition table. First boot needs `boot_a` and `super`, because that's where it finds your unit's firmware.

## 1. Stop at the U-Boot prompt

Hand-typing often misses the countdown, so use the included checker, which sends keys for you. Start it first, then power on the mirror:

```sh
pip install pyserial
python3 uart-check.py /dev/ttyUSB0            # macOS: /dev/cu.usbserial-XXXX
```

It stops autoboot and prints PASS, `?` or FAIL for each item. It only reads information. It also leaves the board sitting at the prompt, so open a serial terminal for the next steps:

```sh
screen /dev/ttyUSB0 115200                    # press Enter to see u-boot=>
```

How to read the results:

| Result | Meaning |
|---|---|
| All PASS | The SoC, RAM, eMMC, bootloader and partitions match the reference unit |
| `?` | That line got garbled on the serial link, which is common. Run it again if you like; the flash tool reads the real partition table anyway |
| FAIL | This board differs from the reference unit. Stop and open an issue with `uart-check.log` |

U-Boot on this board can't see the speakers, camera or display, so step 7 checks those.

The check is optional. If you skip it, just interrupt the countdown however you like.

## 2. Back up your whole eMMC

**Don't skip this.** Your backup is the only way back to stock Android.

At the prompt, turn the eMMC into a USB disk. This command keeps running, and that's expected:

```
u-boot=> ums 0 mmc 2
```

**Find the disk on your PC.** It's about 14.6 GiB, with 12 partitions. macOS may say the disk isn't readable; choose **Ignore**, not Initialize.

```sh
lsblk                 # Linux: e.g. /dev/sdb
diskutil list         # macOS: e.g. /dev/disk4
```

**Copy all of it**, replacing the name with yours and double-checking it first:

```sh
# Linux
sudo dd if=/dev/sdX of=mirror-backup.img bs=4M status=progress

# macOS (rdisk is much faster; Terminal may need removable-volume permission)
sudo dd if=/dev/rdisk4 of=mirror-backup.img bs=4m status=progress
```

**Check the copy.** Run the same hash on the disk and the file; the two must match:

```sh
sudo sha256sum /dev/sdX mirror-backup.img       # Linux
sudo shasum -a 256 /dev/rdisk4 mirror-backup.img   # macOS
```

Keep the backup somewhere safe, ideally in two places.

## 3. Download the image

Get the files below and `SHA256SUMS` from the **[latest release](https://github.com/ikiiftekhar2/lemonademirror/releases/latest)** into one folder, then verify them. The release also has the kernel package files, which this install doesn't need separately.

```sh
sha256sum -c --ignore-missing SHA256SUMS            # Linux
shasum -a 256 -c --ignore-missing SHA256SUMS        # macOS
```

| File | What it is |
|---|---|
| `flash-mirror.sh`, `flash-mirror.py` | The flash tool |
| `uart-check.py` | The board check from step 1 |
| `mirror-rootfs.img.xz` | The system. No need to decompress it; the tool does that |
| `mirror-boot.img` | Kernel and device tree |

## 4. Burn it

Leave `ums 0 mmc 2` running, then:

```sh
sudo ./flash-mirror.sh /dev/sdX        # Linux
sudo ./flash-mirror.sh /dev/rdisk4     # macOS
```

On Linux, if your desktop auto-mounted any partition, unmount it first; the tool will tell you.

The tool will:
1. **Check it's really a Mirror V1.1,** and stop if the layout is wrong or Android's partitions are missing.
2. **Ask you to type `I HAVE A BACKUP`.**
3. **Ask for your settings:** Wi-Fi name and password, a password for the `mirror` login (8+ characters), and optionally a hostname, time zone and SSH public key.
4. **Save your current `boot_b`** next to the image files, as a small extra safety net.
5. **Write and verify,** reading everything back to compare. This takes a few minutes.

If it reports a mismatch, don't reboot. Run it again.

## 5. Tell U-Boot to boot it

Press **Ctrl+C** in the serial terminal to leave USB mode, then run these one at a time:

```
u-boot=> setenv bootcmd 'mmc dev 2; fatload mmc 2:4 0x40800000 /boot.scr; source 0x40800000'
u-boot=> printenv bootcmd
u-boot=> saveenv
```

**Check the `printenv` output before you run `saveenv`.** The serial link can drop characters, so if it doesn't match exactly, run `setenv` again.

## 6. First boot

Cut the power, wait a few seconds and plug it back in. You can disconnect the UART and USB now, though the UART is handy for watching this first time.

**The screen stays dark,** as designed. This is what's happening:

1. It extracts the firmware from your own Android partitions.
2. It sets up your Wi-Fi, login, hostname and SSH keys.
3. It wipes your settings from the boot partition, and grows the filesystem to fill the partition.
4. It restarts once, so the drivers can load the firmware, and joins your Wi-Fi.

Allow a few minutes.

## 7. Log in and check the hardware

```sh
ssh mirror@mirror               # or: ssh mirror@<IP from your router>
sudo mirror-hwcheck
```

`mirror-hwcheck` checks the display link, camera, audio devices, firmware, Wi-Fi, Bluetooth, button and reboot fix. It should say 20 of 20. If only the camera fails on the very first boot, cut the power, plug it back in and run it again; that happened once on real hardware and the power cycle cleared it.

Then check what it can't judge:

```sh
screenon 80                                                 # light the screen
echo 0 | sudo tee /sys/class/graphics/fbcon/cursor_blink    # hide the console cursor
cat /usr/local/share/mirror/testcard.bgra | sudo tee /dev/fb0 >/dev/null   # test card
speaker-test -D default -c 2 -t wav -l 1                    # sound
arecord -D default -d 5 -f S16_LE -r 48000 -c 2 /tmp/mic.wav && aplay -D default /tmp/mic.wav   # mic: talk for 5 s
screenoff                                                   # back to dark
echo 1 | sudo tee /sys/class/graphics/fbcon/cursor_blink    # cursor back on
```

The test card should be upright, with the red, green, blue and white squares in the right colours. The red frames at 0 and 10 px sit under the bezel, so it's normal not to see them. Keep your content at least 20 px (the yellow frame) from every edge.

If you skip the `cursor_blink` line, a blinking cursor shows near the top of the test card. That's the text console, which shares the screen; it's harmless.

Now see the [developer guide](developer-guide.md) to start building on it.

## Everyday use

| To do this | Run or do this |
|---|---|
| Reach it as `mirror.local` | Not set up in the image. [Install it once](developer-guide.md#platform-behaviour) |
| Reboot | `sudo reboot`. Back on SSH in about 40 s |
| Turn off | `sudo shutdown now`. Only wall power turns it back on |
| Screen on / off | `screenon 80` / `screenoff`. It always boots dark |
| Pair a phone | `sudo mirror-bt-pair`, then pick your mirror's hostname (**mirror** unless you chose another) on the phone within 2 minutes. [Details](developer-guide.md#bluetooth) |
| Use the button in an app | [Developer guide](developer-guide.md#bottom-button). It isn't a power button; just avoid holding it for 5 s or more |

## Troubleshooting

**The mirror never appears on the network.** Check these in order:
1. **Power:** use a good outlet. These boards can fail to boot on a weak or shared one.
2. **Wait longer,** then power-cycle once. First boot retries on each power-up until it succeeds.
3. **Look at the UART,** which shows first-boot messages and has a login prompt for `mirror`.
4. **Read the log:** if first boot failed, the reason is in `mirror-firstboot.log` on the `boot_b` partition. To read it, go back to `ums 0 mmc 2` and mount partition 4 on your PC.

**Wrong Wi-Fi details:** log in over the UART and run:
```sh
sudo nmcli dev wifi connect "YOUR NETWORK" password "YOUR PASSWORD"
```

**`amp tables not found in boot_a`:** your unit has different Android firmware from the reference unit, so first boot can't find the speaker tables and stops. Please open an issue. A warning that a Wi-Fi or Bluetooth file "differs" isn't fatal, but mention it in an issue too.

**The tool says "partition isn't where a Mirror V1.1 keeps it":** it's protecting your board, or you've pointed it at the wrong disk. Check the disk name. If it's the right one, your unit differs, so please open an issue.

**It boots to the U-Boot prompt instead of Linux:** `bootcmd` probably didn't save correctly. Repeat step 5.

**The UART login shows nothing, or garbage:** check that TX and RX are crossed and the adapter is at 1.8 V and 115200.

## Going back to stock Android

At the prompt, restore the stock boot command and expose the eMMC:
```
u-boot=> setenv bootcmd 'boota mmc2'
u-boot=> saveenv
u-boot=> ums 0 mmc 2
```

Then write your backup back, checking the disk name carefully:
```sh
sudo dd if=mirror-backup.img of=/dev/sdX bs=4M status=progress conv=fsync    # Linux
sudo dd if=mirror-backup.img of=/dev/rdisk4 bs=4m status=progress            # macOS
```

Press Ctrl+C on the console and power-cycle. This restore path hasn't been tested end to end with this image, so treat your backup as precious.

## How it works

**Why only two partitions change.** Secure boot locks the bootloader, so we keep it. Stock U-Boot can load any kernel you point it at, so we reuse the existing partition table:

```
ROM → SPL → ATF → stock U-Boot → boot.scr → Linux → Debian
                                    │          │       │
                     boot_b (FAT): boot.scr, Image, DTB │
                                            userdata (ext4): Debian
```

**Why a U-Boot command is the final step.** Saving `bootcmd` is what switches the mirror from Android to Linux, and the flash tool can't do that from USB mode.

**How your settings get in.** `mirror-boot.img` has reserved space for a boot script and a settings file. The tool fills in your settings and your unit's partition ID in memory, then writes the result. That's why you don't need to mount anything, and it works the same on Linux and macOS.

**Why no firmware is included.** The Wi-Fi, Bluetooth and amp firmware belongs to its vendors, so this project doesn't redistribute it. Your mirror already has it: first boot finds `vendor_a` from Android's partition metadata, copies the Wi-Fi and Bluetooth files, and finds the two amp tables inside the Android kernel in `boot_a`.

**What's different from Android's drivers:** see [STATUS](STATUS.md) and the [driver notes](drivers/). The ones most likely to matter:
- [Display](drivers/D3-display.md): a bridge patch using the vendor's register values.
- [Button](drivers/D1-D2-D7-D8-D9-misc.md#d8--bottom-button-): the driver polls, because the secure firmware blocks the writes its interrupt needs.
- [Reboot](drivers/reboot.md): a shutdown hook goes straight to a firmware reset, because the kernel's own path gets stuck.

**Security.** The image has no Wi-Fi details, passwords, SSH keys or firmware in it. Accounts stay locked until first boot, and root can't log in over SSH. Your passwords sit in plain text on the boot partition until first boot wipes them, so don't hand the board to anyone before then. If you gave an SSH key, password login over SSH is turned off.

## What has been tested

| Test | Result |
|---|---|
| Real U-Boot in an emulator ran `boot.scr` and booted the real kernel, on a fake eMMC made from the reference unit's partition table, `boot_a` and `super` | ✅ 31 of 31 checks |
| First boot in that emulator: firmware, Wi-Fi profile, login, wipe, resize, reboot | ✅ |
| Firmware extraction on a real mirror | ✅ 7 of 7 files byte-identical to its working firmware |
| `mirror-hwcheck` on a real mirror | ✅ 20 of 20 |
| Kernel, DTB, drivers, tools and configs in the image, compared with a working mirror | ✅ 21 of 21 match |
| Flash tool on macOS and Linux against a disk file or loop device, including refusing four kinds of bad disk | ✅ |
| **Real hardware:** `uart-check.py` on a second Mirror V1.1 | ✅ 9 of 9, same as the reference unit |
| **Real hardware:** that unit's Android device tree (`dtbo_a`), read over `ums` and decompiled | ✅ byte-identical to the reference unit's |
| **Real hardware:** flash tool on macOS against that unit's real `ums` disk, write and read-back verify | ✅ |
| **Real hardware:** first boot on that unit: firmware from its own Android partitions, Wi-Fi, login, SSH | ✅ |
| **Real hardware:** `mirror-hwcheck` on that unit | ✅ 20 of 20 after a power cycle. On the very first boot the camera gave no frames; everything else passed |
| **Real hardware:** test card on the glass, left and right speakers, both mics, on that unit | ✅ by eye and ear |
| **Real hardware:** live mirrored camera view on the glass (mpv, DRM) on that unit | ✅ by eye |
| **Real hardware:** bottom button tap, double and hold on that unit | ✅ all three events |
| **Real hardware:** pairing an iPhone with `mirror-bt-pair` on that unit | ✅ paired; the window closed itself afterwards |

**Not tested yet:**
- The flash tool on a real `ums` disk on Linux. The real burn was from macOS.
- More units. One second unit has been burned so far.
- Restoring the backup after flashing.

If you try it, please [tell us how it went](https://github.com/ikiiftekhar2/lemonademirror/issues), even if it just worked.

## Build the image yourself

On a Debian or Ubuntu PC, with `debootstrap`, `qemu-user-static`, `dosfstools` and `xz-utils` installed:
```sh
sudo image/build-image.sh       # about 30 minutes; output in image-build/dist/
```
The kernel and modules come from [`prebuilt/`](../prebuilt/). Source for those is Linux 6.18.60 plus [`kernel/patches/`](../kernel/patches/). To build them yourself, see [Build the kernel](02-build-kernel.md).
