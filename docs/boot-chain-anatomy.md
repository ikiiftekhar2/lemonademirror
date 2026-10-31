# Hunting the SPL and decoding the boot chain from your dumps

Understanding where the bootloader lives on this board is worth doing before you flash anything — it
tells you what's safe to touch, where the stock U-Boot comes from, and gives you the signed SPL if you
need it for the SDP recovery path. All of this is read-only analysis of **your own** eMMC dump.

> The actual secure-boot/SDP *bypass* used to get initial access is covered by the external guide
> (credit **gouda-percha**, [01-get-uboot.md](01-get-uboot.md)). This page is about **finding and
> reading** the boot components in your dump — so you know the layout and can carve the signed SPL.

## Key fact: the SPL is not in a normal partition

On the i.MX8MM the whole secondary boot chain lives in the eMMC **boot0 hardware partition**
(`mmcblk2boot0`), not in any GPT/user partition. That's why [step 1](01-get-uboot.md) dumps the boot
partitions separately:
```sh
adb exec-out "dd if=/dev/block/mmcblk2boot0 bs=4M" > boot0.img
adb exec-out "dd if=/dev/block/mmcblk2boot1 bs=4M" > boot1.img
```
If you only imaged the GPT (`mmcblk2`), you **don't** have the SPL — the user area at these offsets is
just padding. Grab `boot0`.

## What's inside boot0 (a flash-image container)

`boot0.img` is an NXP `flash.bin`-style container: a signed SPL, then a FIT/ITS that points at U-Boot
proper, ATF (BL31) and OP-TEE. On the reference unit (build `2020.04-00004-gfbe316d`, Apr 2021) the
layout was:

| Region | boot0 offset | Loads at | How to find it |
|---|---|---|---|
| IVT header | `0x8400` | — | the image vector table (entry/load/CSF pointers) |
| **SPL binary** | `0x8000` (entry `0x8440`) | TCML `~0x7E1000` | banner string `U-Boot SPL 2020.04…` |
| SPL FIT/ITS | `0x60000` | — | FDT magic `d0 0d fe ed`; says "load ATF before U-Boot" |
| **U-Boot proper** | `0x63000` | — | banner `U-Boot 2020.04…` |
| U-Boot DTB | `~0x13B198` | — | FDT magic |
| ATF (BL31) | `~0x143CD0` | `0x920000` | — |
| OP-TEE | `~0x14EEC0` | `0xBE000000` | — |

Offsets vary by build date, so **hunt by content, not fixed numbers**.

## How to hunt (works on any unit)

```sh
# 1. find the banner strings -> confirms SPL and U-Boot are present and their build
strings -t x boot0.img | grep -iE "U-Boot (SPL )?20[0-9]{2}\."
#    e.g.  00008xxx  U-Boot SPL 2020.04-...
#          00063xxx  U-Boot 2020.04-...

# 2. find the device trees / FIT (FDT magic d00dfeed)
grep -abo $'\xd0\x0d\xfe\xed' boot0.img        # offsets of each DTB / the ITS

# 3. let binwalk map the whole container
binwalk boot0.img

# 4. carve the signed SPL (start of boot0 through the FIT), keep a hash
dd if=boot0.img of=spl.img bs=1 count=$((0x60000))
sha256sum spl.img
```
To disassemble the SPL (e.g. in Ghidra / REA / Hopper), wrap the payload at `0x8000` in a minimal
ELF64/aarch64 header with the load/entry addresses from the IVT — the same wrap-in-ELF trick used for
the vendor kernel in [00-reverse-engineering.md](00-reverse-engineering.md).

## Why this matters for the port

- **boot0 is HAB-signed and the secure-boot fuses are closed.** You can't replace the SPL or U-Boot
  persistently — a modified boot0 fails authentication. So the strategy here is: **keep the stock,
  signed SPL + U-Boot untouched, and boot your own kernel from the user area through the stock U-Boot**
  (the saved-env + `boot.scr` approach in [04-flash-and-persist.md](04-flash-and-persist.md)). That's
  the whole reason the flash step never writes boot0.
- The carved, signed `spl.img` is what the SDP recovery flow in the external guide feeds to the ROM
  (the ROM only accepts a correctly-signed SPL). Having your own copy means you're not dependent on
  anyone else's image, and the byte-exact SPL matches your unit's build.
- Knowing ATF loads at `0x920000` and OP-TEE at `0xBE000000` also explains two things you'll see on
  mainline: the `reserved-memory` ranges you must honour (so Linux doesn't stomp OP-TEE — see
  [D10 fix 3](drivers/D10-camera.md)) and the harmless `caam_probe` oops (the crypto block is owned by
  the secure world).

## Safety

- **Never write boot0/boot1.** Read them, analyse them, keep the SPL image — but flashing them risks a
  brick that only JTAG/SDP can recover, and a modified image won't pass HAB anyway.
- Always keep your full `mmcblk2_stock.img` plus `boot0.img`/`boot1.img` as the restore set.
