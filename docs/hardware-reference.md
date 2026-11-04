# Hardware reference (so you can follow along if you have the same modules)

Everything below was read off a real unit (device-tree `model = "lululemon Mirror V1.1"`). Your unit
should match if it's the same generation; **verify chip markings and I²C addresses on your own board
before trusting any of it** — vendors do silent component swaps.

## SoC / board

| | |
|---|---|
| SoC | **NXP i.MX8M Mini**, part `MIMX8MM6DVTLZAA` (consumer, Vivante GPU). 4× Cortex-A53 |
| GPU | Vivante **GC600** (etnaviv), OpenGL **ES 2.0** only |
| Video codec | **Hantro** G1 (`38300000.video-codec`, H.264 8-bit / VP8 / MPEG-2 decode) + G2 (`38310000`, HEVC / VP9). **No hardware encoder** in mainline. |
| RAM | 2 GiB LPDDR4 (`MemTotal` ≈ 1.98 GB) |
| eMMC | ~16 GiB (Kingston `imem0`), controller `mmcblk2`, on `usdhc3` |
| PMIC | **NXP PCA9450** on **I²C1 @ 0x25** (variant suffix unconfirmed; EVK ships `pca9450a`) |
| Boot | ROM → SPL → ATF (BL31) → U-Boot 2020.04 → (stock: Android / TEE). **HAB is closed** (secure boot fuses burned) — you can't replace the signed SPL, which is why the access method in [01-get-uboot.md](01-get-uboot.md) matters. |

## I²C bus map

The i.MX8MM has 4 I²C controllers. On this board:

| Bus | Controller | Speed | Devices (address) |
|---|---|---|---|
| I²C1 | `30a20000.i2c` | 400 kHz | PMIC PCA9450 **@0x25** |
| I²C2 | `30a30000.i2c` | 400 kHz | DSI→LVDS bridge SN65DSI83/84 **@0x2c** |
| I²C3 | `30a40000.i2c` | 100 kHz | camera OV5640 **@0x3c** |
| I²C4 | `30a50000.i2c` | 400 kHz | amp "tweeters" **@0x2c**, amp "woofers" **@0x2f** |

(Live check: `i2cdetect -y -r <bus>` — every expected address shows `UU`, i.e. a kernel driver is
bound. A full scan finding **only** these addresses is also how D9 was closed: there is no touch
controller.)

## Display

| | |
|---|---|
| Bridge | **TI SN65DSI83** (DSI→LVDS), I²C2 @0x2c, enable GPIO. *The vendor device tree labels it SN65DSI84; the mainline `ti-sn65dsi83` driver drives it fine.* |
| Panel | **1920×1080 dual-link LVDS**, 941×529 mm, `compatible = "tn,hj070na…"` (panel-lvds), 60 Hz |
| Orientation | panel is **landscape glass mounted 90° clockwise** in a portrait body → render portrait (1080×1920) and rotate **90° CCW** |
| Display controller | i.MX8MM **LCDIF** → `mxsfb` DRM driver (`32e00000.lcdif`), connector `LVDS-1` |
| Backlight | `pwm-backlight` on PWM `30670000.pwm`, 1 kHz, inverse polarity, 101 levels (0 = off) |
| ⚠️ gotcha | DRM card numbers (`card0`/`card1`) **swap between boots**; use `/dev/dri/by-path/platform-32e00000.lcdif-card` |

## Audio

| | |
|---|---|
| Amps | **2× TI TAS5806MD** class-D, I²C4 @0x2c (left/"tweeters") and @0x2f (right/"woofers"), fed by **SAI1** (I²S, 2 slots × 16-bit) |
| Amp MCLK | **49.152 MHz** (SAI1 root ← AUDIO_PLL); amp PDN & fault on GPIO4 lines |
| Amp "firmware" | each amp runs a **3264-byte vendor DSP register table** (extracted from the vendor kernel; see [D4](drivers/D4-speakers.md)) |
| Mic | I²S MEMS mic(s) on **SAI5** (clock master), 48 kHz; exposed via `dmic-codec` in `imx-card` |
| Mic MCLK | SAI5 must **drive** its MCLK pad (`fsl,sai-mclk-direction-output`) — the one-line D5 fix |

## Camera

| | |
|---|---|
| Sensor | **OmniVision OV5640**, 5 MP, wide-angle lens, I²C3 @0x3c |
| Interface | MIPI **CSI-2, 2 data lanes** → `imx-mipi-csis` (`32e30000.mipi-csi`) → `imx7-media-csi` (`32e20000.csi`) → `/dev/video0` |
| MCLK | **24 MHz**, routed on a pad from ANAMIX_REF_CLK_24M (GPIO1_IO01), free-running |
| Modes | 2592×1944@15, 1920×1080@30 (centre crop), 1280×720@30, 640×480@60; pixel format `UYVY8_1X16` over the bus |
| Power/reset | PWDN GPIO1_IO07 (active-high), RESET GPIO1_IO06 (active-low) |

## Wireless

| | |
|---|---|
| Combo chip | **Broadcom/Cypress BCM4345/6** (CYW43455-class) |
| WiFi | on **SDIO / usdhc1**, driver `brcmfmac`, firmware 7.45.214; VMMC regulator must be **3.3 V** (the key D6 fix). Needs `brcmfmac43455-sdio.{bin,txt,clm_blob}` + board NVRAM |
| Bluetooth | on **UART1** (`30860000.serial`), driver `hci_uart`/bcm, patch file `BCM4345C0.hcd`, 3 Mbaud. BT_REG_ON = GPIO2_IO06, **active high** in mainline (D7) |

## Other GPIO / input

| | |
|---|---|
| Bottom button | SNVS ONOFF pad, `snvs_pwrkey` (polled), emits **`KEY_PROG1`** (D8). A separate `gpio-keys` line (GPIO5_IO28, "Factory Reset") is also ported, but no press has been seen on it. |
| Touch | **none** — no touch controller exists on this board |
| RTC | **no battery-backed RTC** — the clock starts near 1970 until NTP syncs |

## Useful live commands

```sh
cat /proc/device-tree/model                 # "lululemon Mirror V1.1"
i2cdetect -y -r 4                            # amps at 0x2c / 0x2f
v4l2-ctl --list-devices                      # camera + VPU decoders
aplay -l ; arecord -l                        # audio card
cat /sys/class/backlight/backlight/max_brightness   # 100
media-ctl -p -d /dev/media0                  # camera pipeline
```
