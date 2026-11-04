# Hardware status (D1–D10 and friends)

Legend: ✅ working · 🟡 partial / unconfirmed · 🔴 not working · ⏸ parked (works but not the goal)

| # | Block | Status | Root cause → fix | How it was verified |
|---|-------|--------|------------------|---------------------|
| D1 | Serial console (UART2 / `ttymxc1`) | ✅ | 115200 8N1 on the A53 UART; kernel `console=ttymxc1,115200` | login prompt + root shell over USB-UART |
| D2 | eMMC storage | ✅ | our rootfs lives on the former `userdata` partition; boot files on a small FAT partition | all partitions mount; read-back hashes match |
| D3 | Display (SN65DSI83 bridge + LVDS panel) | ✅ | mainline `ti-sn65dsi83` derives the LVDS output-stage registers wrong for this panel → **override patch** writes the 8 vendor register values; panel is landscape glass mounted 90° CW → content pre-rotated 90° CCW (`fbcon=rotate:3` + `CONFIG_FRAMEBUFFER_CONSOLE_ROTATION=y`) | panel locks; test card upright; colours correct |
| D3b | Backlight | ✅ | `pwm-backlight`, brightness 0–100, 0 = off; independent of the display driver; boots dark via a service | brightness ramp + modeset tests |
| D4 | Speakers (2× TAS5806) | ✅ | vendor DSP register tables loaded as firmware; driver: load-once, fault-clear, **volume capped at −12 dB** (the "distortion" was the mixer at +48 dB); PDN polarity; S16 format; TDM 2×16 | listening tests (L/R, levels) |
| D5 | Microphone (SAI5 I²S) | ✅ | SAI5 took its clock from an undriven pad → add `fsl,sai-mclk-direction-output` to the device tree | record + playback |
| D6 | WiFi (BCM4345/6 on SDIO) | ✅ | (a) stop two drivers claiming the same pin, (b) restore the regulator's own pinctrl, (c) regulator 1.8 → 3.3 V so the SDIO card's voltage is supported; NetworkManager profile baked into the image | autoconnects every boot; DHCP + SSH |
| D7 | Bluetooth (BCM4345C0 on UART1) | ✅ | power-pin polarity and UART clock mux fixed; scans, iPhone paired and stayed connected. Not tested: reconnect, second-device refusal. No profiles offered yet. |
| D8 | Bottom button | ✅ | SNVS ONOFF pad, polled; `mirror-buttond` gives `tap`/`double`/`hold`. Verified with real presses after a cold boot. |
| D9 | Touch | ✅ (none) | I²C scan finds only PMIC / bridge / camera / amps — there is no touch controller; the vendor's touch config file is a leftover | i2cdetect on all buses |
| D10 | Camera (OV5640 MIPI CSI-2) | ✅ | fix the format chain (`UYVY8_1X16`); then a **camera hub** (one owner + v4l2loopback) so any number of apps/ML models read it at 1080p30; capture buffers made cacheable so the CPU copy is cheap | 4–6 concurrent readers at full rate |
| — | Memory (CMA pool) | ✅ | device-tree `reserved-memory` was missing `ranges;`, so the whole node (incl. CMA + secure-firmware reservations) was ignored → add it; CMA now 128 MiB, camera capped at 32 MiB | dmesg reservations; cold boot |
| — | System time | ✅ | `systemd-timesyncd` wasn't installed (clock stuck near 1970, cron pegged a core) → install + NTP | `timedatectl` synced |
| — | Unattended cold boot | ✅ | saved U-Boot env loads a boot script; WiFi autoconnects | up + SSH ~30–60 s after power-on, repeatedly |
| — | `caam_probe` kernel oops | 🟡 harmless | crypto block is owned by the secure firmware; oops every boot, system runs fine | dmesg; blacklisting `caam` silences it |
| — | `reboot` over SSH | 🟡 | hangs (board parks); cause unconfirmed → use `poweroff` + power-cycle | — |
| — | Video on the panel | ⏸ | HW H.264 decode works (~24 fps, ~19% CPU) but display path is ~1 fps; it's a UI device, not a media player | GStreamer measurements |

Full per-block write-ups are under [docs/drivers/](drivers/).
