# D6 — WiFi: SDIO pinctrl + regulator voltage

**Status: ✅ working.** Autoconnects at boot, DHCP, SSH reachable headlessly. No kernel patch — all
device-tree + firmware + a NetworkManager profile.

## Hardware
**Broadcom/Cypress BCM4345/6** (CYW43455-class) combo chip. WiFi is on **SDIO** via the `usdhc1`
controller; driver **`brcmfmac`**, firmware 7.45.214. The chip is powered/reset through a regulator
`reg_wlreg_on` on a GPIO that is **also** the `vmmc-supply` for `usdhc1`.

## Three bugs, fixed one boot at a time
(Classic DT debugging — read the kernel log, fix the one error it names, repeat.)

1. **No `wlan0`, no SDIO device.** Log: `pin … SD1_RESET_B already requested by regulator-wlreg-on;
   cannot claim for … mmc`. The device tree listed the same `pinctrl_wlreg_on` group **both** in all
   three `&usdhc1` pinctrl states **and** in the regulator. → Remove it from the `usdhc1` states;
   the regulator owns that pin.
2. **`SD1_CLK already requested`.** An over-eager fix had rewritten the regulator's pinctrl too.
   Checking the **vendor** DT showed the right split: `usdhc1` uses its own data/clock pin groups, and
   the regulator keeps only its own `pinctrl-0 = <&pinctrl_wlreg_on>` plus `gpio = <&gpio2 10>`. →
   Restore exactly that.
3. **`mmc0: error -22 … no support for card's volts`.** The regulator was declared **1.8 V** (copied
   from the vendor DT), but the SDIO card negotiation needs a 3.3 V-capable `vmmc`. → Set the
   regulator to **3300000 µV**.

After #3: `brcmfmac: using brcm/brcmfmac43455-sdio for chip BCM4345/6`, firmware loads, scan works.

## Firmware
`/lib/firmware/brcm/`: `brcmfmac43455-sdio.bin`, `.txt` (NVRAM), `.clm_blob`, plus the board-specific
NVRAM. These are vendor/Broadcom files — **not** in this repo; pull them from your backup
([05-extract-vendor-blobs.md](../05-extract-vendor-blobs.md)). `regulatory.db` is missing and causes
harmless `set chanspec … fail` log spam.

## Autoconnect
The rootfs ships a NetworkManager keyfile that connects at boot; populate
[`rootfs/templates/wifi.nmconnection.template`](../../rootfs/templates/wifi.nmconnection.template)
with your SSID/PSK at build time (see [03-build-rootfs.md](../03-build-rootfs.md)).

Once root has a writable filesystem you can also just:
```sh
nmcli dev wifi connect "YOUR_SSID" password "YOUR_PASSWORD"
```
The address is DHCP (no static IP), so find the mirror by its DHCP lease / your router, or
[set up `mirror.local`](../developer-guide.md#platform-behaviour) (mDNS isn't installed by default).
