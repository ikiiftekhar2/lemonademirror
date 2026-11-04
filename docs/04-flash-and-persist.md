# 4. Flash the eMMC and make it boot your Linux

> **Don't want to build anything?** [Flash the ready-made image](06-flash-image.md) instead. This page is for your own build.

The stock bootloader (U-Boot) stays in place. We write our kernel + rootfs onto the eMMC and save a
U-Boot environment that boots them on every power-on. The ROM boot partitions are never touched.

## Partition plan
We reuse the existing GPT instead of repartitioning:
- a small **FAT** partition (the old `boot_b`, ~64 MiB) holds `Image`, `imx8mm-mirror.dtb`, `boot.scr`;
- the big **`userdata`** partition becomes our ext4 **rootfs**.

## Expose the eMMC from U-Boot
At the `u-boot=>` prompt:
```
u-boot=> ums 0 mmc 2
```
The eMMC now appears on your PC as a USB disk (`/dev/sdX`, or `diskN` on macOS) with all the stock
partitions visible.

## Write the images (from your PC)
```sh
# rootfs → the userdata partition (find it by size/label, verify the target!)
sudo dd if=mirror-rootfs.img of=/dev/sdXN bs=4M status=progress conv=fsync

# kernel + dtb + boot script → the FAT boot partition
sudo mount /dev/sdXM /mnt
sudo cp Image imx8mm-mirror.dtb boot.scr /mnt/
sudo umount /mnt
```
Always confirm the target partition by label/size before `dd`. Read back and hash-compare if you want
to be sure.

## The boot script
U-Boot runs a compiled `boot.scr`. Build it from the template with the helper script (it needs your
rootfs partition's **PARTUUID**):
```sh
# find the PARTUUID of the rootfs partition you just wrote:
lsblk -o NAME,PARTUUID /dev/sdX
# build boot.scr:
scripts/make-bootscr.sh <ROOTFS_PARTUUID>      # produces boot.scr
```
The script (template [`rootfs/templates/boot.cmd.template`](../../rootfs/templates/boot.cmd.template))
sets the kernel command line — including `fbcon=rotate:3` for the sideways panel — loads `Image` and
the dtb from the FAT partition, and boots.

## Save the U-Boot environment
So it boots this on every power-on, set a short bootcmd and save it:
```
u-boot=> setenv bootcmd 'mmc dev 2; fatload mmc 2:4 0x40800000 /boot.scr; source 0x40800000'
u-boot=> saveenv
```
> Keep the `bootcmd` short. The serial console is lossy at 115200, and a long multi-command `setenv`
> can get truncated mid-save — hence the one-liner that just sources `boot.scr`.

## Verify
Power-cycle with nothing attached. The mirror should boot your Linux, join WiFi, and be SSH-reachable
in ~30–60 s. (It boots with the **backlight off** by design — that's the `screen-off` service; turn
it on with `screenon 80`.)

## Notes & gotchas
- **`reboot` over SSH works** with the overlay's shutdown hook installed ([details](drivers/reboot.md)). Without it, the board hangs and needs a power-cycle.
- If a bad kernel won't boot: `ums 0 mmc 2` again, mount the FAT partition, copy a known-good `Image`
  back. Keep your last-good `Image`/`dtb`.
- Full restore to stock: `dd` your `mmcblk2_stock.img` back over the whole eMMC.

## Using the prebuilt binaries
If your board is the same revision, you can skip building and use [`prebuilt/`](../prebuilt/):
`Image`, `imx8mm-mirror.dtb`, and `modules-6.18.60-dirty.tar.gz` (untar into `/lib/modules/` in your
rootfs). The module `vermagic` is `6.18.60-dirty` and must match the `Image` — use them as a set. You
still need the vendor firmware blobs ([step 5](05-extract-vendor-blobs.md)).

Next: [extract the vendor firmware blobs](05-extract-vendor-blobs.md).
