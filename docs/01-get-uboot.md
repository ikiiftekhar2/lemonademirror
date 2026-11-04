# 1. Get a U-Boot prompt, and back up your stock firmware

## Access (external — credit: gouda-percha)

Getting bootloader/root access on a **locked** unit (HAB secure boot is enabled; you can't just flash
your own bootloader) was figured out by **gouda-percha** and is written up here:

### 👉 https://failedattempts.neocities.org/

**Do that first.** It covers the JTAG/SDP route to a root shell and a U-Boot prompt on the locked
hardware. This project picks up *after* you can reach the `u-boot=>` prompt over the serial console.

This repo does **not** re-document that access work — follow the guide above, and thank gouda-percha.

## Reaching U-Boot once you have access
With a 1.8 V USB-UART adapter on the A53 UART (115200 8N1), watch the boot and **interrupt the
autoboot countdown** (spam a key / send bytes as it counts down) to drop to the `u-boot=>` prompt.
A tiny pyserial script that streams bytes at power-on is more reliable than hammering a key by hand.

## Back up the stock eMMC (do not skip)
Before you change anything, dump the stock firmware so you can always return to a 100% original
Android mirror. From a **root ADB shell** on the stock system (per the guide above):

```sh
adb exec-out "dd if=/dev/block/mmcblk2 bs=4M"  > mmcblk2_stock.img     # whole eMMC (~16 GiB)
# and the individual boot partitions, handy for analysis / selective restore:
adb exec-out "dd if=/dev/block/by-name/boot_a   bs=1M" > boot_a.img
adb exec-out "dd if=/dev/block/by-name/dtbo_a   bs=1M" > dtbo_a.img
adb exec-out "dd if=/dev/block/by-name/vendor_a bs=1M" > vendor_a.img
```

Or, from U-Boot, expose the eMMC as a USB disk and image it from your PC:
```
u-boot=> ums 0 mmc 2        # eMMC now appears as a USB mass-storage device on your computer
# then on the PC:  sudo dd if=/dev/sdX of=mmcblk2_stock.img bs=4M status=progress
```

**Keep `mmcblk2_stock.img` safe (ideally two copies).** It is:
- your restore image (`dd` it back → stock Android), and
- the source for the vendor firmware blobs this project needs
  ([05-extract-vendor-blobs.md](05-extract-vendor-blobs.md)).

Full restore later is just the reverse `dd`. The signed ROM boot partitions (`boot0`/`boot1`) are
never touched by this project.

Next: [flash the ready-made image](06-flash-image.md), or [build the kernel](02-build-kernel.md) yourself.
