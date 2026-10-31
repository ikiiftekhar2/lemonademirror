# D1, D2, D7, D8, D9 — console, storage, Bluetooth, button, touch

## D1 — Serial console ✅
UART2 (`ttymxc1`), **115200 8N1**, on the A53 UART header. Kernel `console=ttymxc1,115200`; you get a
root login on the console. This is your lifeline for driving U-Boot and watching boots.

- ⚠️ **The UART pads are 1.8 V.** Use a 1.8 V-capable USB-UART adapter; do **not** feed 3.3/5 V into RX.
- On macOS the serial `stty` can latch at the wrong baud — a small pyserial reader is more reliable
  than `screen`/`minicom` for catching early boot.
- Minor quirk on our image: both `getty@ttymxc1` and `serial-getty@ttymxc1` run on the same port,
  which can garble the login. If the UART login misbehaves: `systemctl disable --now getty@ttymxc1`.

## D2 — eMMC storage ✅
~16 GiB eMMC as `mmcblk2`, GPT with the stock Android partitions. We **repurpose** partitions rather
than repartition: our Debian rootfs goes on the old **`userdata`** partition (ext4), and the kernel +
boot script go on a small **FAT** partition (the old `boot_b`). The signed boot ROM partitions
(`boot0`/`boot1`) are left untouched. See [04-flash-and-persist.md](../04-flash-and-persist.md).

The rootfs filesystem is smaller than its partition (~3.3 GB in a 5.8 GB slot); you can `resize2fs` it
larger if you want the space.

## D7 — Bluetooth 🔴 not working (help wanted)
Same **BCM4345/6** combo chip as WiFi; Bluetooth is on **UART1** (`30860000.serial`), driver
`hci_uart`/bcm, patch file `BCM4345C0.hcd`.

**Symptom:** `hci0` attaches but the controller never answers — `BCM: failed to write update
baudrate`, a `0xfc18` command times out, `hci0` stays DOWN with a zero address.

**Tried:** re-parenting the UART1 root clock (vendor uses SYS_PLL1_80M); the HCD firmware is present.
GPIO toggles don't help because the lines are owned by the driver.

**Likely next steps (untested):** a device-tree variant **without** the serdev child so `/dev/ttymxc0`
is free, then drive the vendor init sequence (`btattach` + the vendor baud-rate/minidriver dance) by
hand; and/or scope the UART on a bench. The vendor's init sequence (switch to 3 Mbaud, load a
minidriver, delay) was decoded from the vendor Bluetooth HAL. **PRs welcome.**

## D8 — Front button 🟡 detected, press unconfirmed
One physical button, exposed via **`gpio-keys`** as `/dev/input/event0` emitting **`KEY_F10`**. There
is no hidden second button.

⚠️ An earlier "it works" came from `evtest --query`, which only reads the key's *current* state and
never captured an actual press. **To confirm:** run `evtest /dev/input/event0`, press the button, and
look for `value 1` / `value 0` events. (Low-risk, just needs a human at the mirror.)

## D9 — Touch ✅ (there is none)
Exhaustive I²C scan of all four buses finds **only** the known chips (PMIC, DSI bridge, camera, two
amps — all driver-bound). There is **no touch controller**. A `Novatek_NT11003` touch config file in
the vendor partition is a platform leftover, not wired to anything. So: interaction is the **camera
(gestures) + the one button**, not touch.

(Caveat: `i2cdetect -y` scans 0x08–0x77; a paranoid re-check with `-a` would also probe the low
reserved addresses, but nothing suggests a device there.)
