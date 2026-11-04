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

## D7 — Bluetooth ✅
**BCM4345C0** (Murata Type-1MW) on **UART1** (`30860000.serial`) at 3 Mbaud, driver `hci_uart`/bcm, patch file
`BCM4345C0.hcd`. Tested on the reference unit: comes up unattended from a cold boot, scans, and an iPhone paired,
bonded and stayed connected.

**Two device-tree bugs kept it dead:**
1. **BT_REG_ON polarity.** The vendor DT marks the line active-low, but the vendor `fsl,mxc_bt_rfkill` driver ignores
   that flag and drives it raw (pulse low 2 ms, high, wait 40 ms). Mainline `hci_bcm` obeys the flag and drives logical
   1 to power on, so porting it literally held the chip in shutdown. The clue: during `hciconfig hci0 up` the pin stayed
   low, the UART showed `tx:0`, and CTS was never asserted. Now `GPIO_ACTIVE_HIGH`.
2. **UART clock.** `assigned-clocks` pointed at the `IMX8MM_CLK_UART1_ROOT` gate, which has no mux, so UART1 stayed at
   24 MHz, too slow for 3 Mbaud. It now targets `IMX8MM_CLK_UART1` (80 MHz, like the vendor).

**Pairing:** see the [developer guide](../developer-guide.md#bluetooth). Hidden by default; an app opens a timed window
with `mirror-bt-pair`. **Not tested:** reconnecting after a toggle or reboot, and refusing a second device. The mirror
offers no profiles yet, so it isn't a speaker or headset.

## D8 — Bottom button ✅
The single button at the bottom is the SoC's **SNVS ONOFF pad**, not the `gpio-keys` line ("Factory Reset", GPIO5_IO28)
this project first ported, which is why no press was ever captured. A monitor reading both lines during real presses
settled it.

**The upstream driver can't be used as is.** The secure firmware blocks non-secure writes to the SNVS LP registers
(`HPCOMR.NPSWA_EN` = 0; the vendor kernel clears the interrupt through a Trusty call). `snvs_pwrkey`'s interrupt could
never be acknowledged, and a press could lock up the board (reasoned from the blocked writes, deliberately not tried).
So patch `0007` polls `HPSR.BTN` every 40 ms instead. Consequences: `power-off-time-sec` has no effect, so the hardware
hold-to-power-off stays at its default, and the button can't wake the board from suspend.

⚠️ **Use the DTB and patched module together.** This DTB with an unpatched `snvs_pwrkey` is the unsafe combination.

It's a generic button: `KEY_PROG1`, so nothing reacts by default. `mirror-buttond` publishes `tap`, `double` and `hold`
events ([developer guide](../developer-guide.md#bottom-button)). Verified with real presses after a cold boot.

On Android, holding the button ≥ 2.5 s rebooted the board (decoded from the vendor kernel).

## D9 — Touch ✅ (there is none)
Exhaustive I²C scan of all four buses finds **only** the known chips (PMIC, DSI bridge, camera, two
amps — all driver-bound). There is **no touch controller**. A `Novatek_NT11003` touch config file in
the vendor partition is a platform leftover, not wired to anything. So: interaction is the **camera
(gestures) + the one button**, not touch.

(Caveat: `i2cdetect -y` scans 0x08–0x77; a paranoid re-check with `-a` would also probe the low
reserved addresses, but nothing suggests a device there.)
