# 5. Extract the vendor firmware blobs from your backup

Two drivers need binary firmware that originates from the stock image and is **not redistributed in
this repo**. You extract them from the eMMC backup you took in [step 1](01-get-uboot.md), so every
blob is from your own device.

| Blob | For | Source in the stock image |
|---|---|---|
| `tas5805m_dsp_tweeters.bin`, `tas5805m_dsp_woofers.bin` | speakers (D4) | the two amp DSP register tables, compiled into the **vendor Android kernel** (`boot_a`) |
| `brcmfmac43455-sdio.bin`, `.txt` (NVRAM), `.clm_blob` | WiFi (D6) | the **vendor partition** firmware directory |
| `BCM4345C0.hcd` | Bluetooth (D7) | same |

## WiFi / BT firmware
These are ordinary files in the vendor filesystem. Loop-mount or extract the vendor partition from
your backup and copy them:
```sh
# from vendor_a.img (ext4) or the mounted vendor partition:
find . -iname 'brcmfmac43455-sdio*' -o -iname 'BCM4345*.hcd'
cp brcmfmac43455-sdio.bin brcmfmac43455-sdio.txt brcmfmac43455-sdio.clm_blob BCM4345C0.hcd \
   <rootfs>/lib/firmware/brcm/
```
The `.txt` is the board NVRAM; `brcmfmac` loads it automatically next to the `.bin`.

## Amp DSP tables (from the vendor kernel)
The amp "DSP program" is two 3264-byte `{reg,val}` tables compiled into the vendor kernel as the
symbols `registers_tweeters` and `registers_woofers`. The helper script reads them out of an
**unstripped vendor `vmlinux` ELF** (resolving the symbols via the kernel's `kallsyms`) and writes the
firmware files:
```sh
scripts/extract-vendor-blobs.sh vmlinux  <rootfs>/lib/firmware/
# writes tas5805m_dsp_tweeters.bin and tas5805m_dsp_woofers.bin, prints each table's sha256
```
To get a `vmlinux` with symbols from `boot_a.img`: unpack the Android boot image, decompress the
kernel payload, then reconstruct an ELF from the built-in `kallsyms` (e.g.
[`vmlinux-to-elf`](https://github.com/marin-m/vmlinux-to-elf)). The script header documents this. It
prints each table's SHA-256 so you can confirm the extraction is intact. (See
[D4](drivers/D4-speakers.md) for how these tables were identified.)

## Why they're not in the repo
These blobs are vendor/NXP/Broadcom-derived; redistributing them is a licensing grey area. Extracting
them from the firmware already on hardware you own is clean. The repo ships everything *around* them —
drivers, device tree, the extraction tooling — so the only vendor bytes on your mirror are ones that
were already there.

Once the blobs are in place, (re)build or update your rootfs and flash
([step 4](04-flash-and-persist.md)). Then see the [developer guide](developer-guide.md) to build on
top.
