# 🍋 LemonadeMirror

**Turn a Lululemon Mirror (the fitness one) into an open Linux device you fully control.**

The Lululemon Mirror ("Studio Mirror") is a wall-hung smart mirror built on an **NXP i.MX8M Mini**
(4× Cortex-A53, 2 GiB RAM, 16 GiB eMMC) with a 1920×1080 LVDS panel, stereo amps, mic array, a
wide-angle camera and WiFi/BT. It shipped running Android and a subscription app. When the service
winds down the hardware is just... a mirror.

This project replaces Android with **plain Debian + a mainline Linux 6.18 kernel**, so the device
becomes a general-purpose Linux computer with a big portrait display, speakers, a microphone and a
camera — a blank canvas for a DIY "magic mirror", a photo frame, a home dashboard, a gesture-driven
UI, whatever you want. Everything here was done on a real unit; the drivers, device tree, kernel
patches and step-by-step process are all in this repo.

> For hardware you own. Reflashing replaces the stock firmware and voids the warranty; take the full
> eMMC backup in step 2 first so you can always restore it.

## Motivation

When the subscription ends, a lot of these mirrors get thrown out — or gutted, with people bolting a
Raspberry Pi or a separate driver board onto the panel just to light it up. That replacement board
often costs about as much as a used mirror, and it throws away hardware that's already there and
already good: a quad-core i.MX8M Mini with 2 GiB of RAM, a 1080p display, stereo amps, a microphone,
a 5 MP camera and WiFi/Bluetooth, all integrated and powered.

The goal of this project is the opposite — **reuse what's already in the box.** Instead of adding
hardware, we put a normal Linux on the computer that's already driving the mirror and bring its
existing sensors and outputs up under mainline drivers. The result is a capable little Linux
appliance with a big portrait screen and a sensor array, for the cost of a UART cable and an
afternoon — nothing thrown away, nothing bolted on.

---

## What works (and what doesn't)

The port is organised as a checklist of hardware blocks, **D1–D10**. Most are done; a couple are
in progress. Each links to a full write-up (symptom → root cause → fix → how it was verified).

| # | Hardware | Status | One-line summary | Details |
|---|----------|--------|------------------|---------|
| D1 | Serial console (UART) | ✅ working | 115200 8N1 on the A53 UART | [misc](docs/drivers/D1-D2-D7-D8-D9-misc.md) |
| D2 | eMMC storage | ✅ working | our rootfs on the old userdata partition | [misc](docs/drivers/D1-D2-D7-D8-D9-misc.md) |
| D3 | Display (DSI→LVDS + panel) | ✅ working | mainline bridge driver programs the wrong LVDS regs → **vendor-register override patch**; panel mounted sideways → rotate 90° CCW | [D3-display](docs/drivers/D3-display.md) |
| D3b | Backlight | ✅ working | PWM 0–100, independent of the display driver, boots dark | [D3-display](docs/drivers/D3-display.md) |
| D4 | Speakers (2× TAS5806) | ✅ working | vendor DSP program + driver fixes; "distortion" was just the mixer at +48 dB | [D4-speakers](docs/drivers/D4-speakers.md) |
| D5 | Microphone (SAI5 I²S) | ✅ working | one device-tree property (`fsl,sai-mclk-direction-output`) | [D5-mic](docs/drivers/D5-mic.md) |
| D6 | WiFi (BCM4345/6) | ✅ working | SDIO pinctrl + regulator voltage fixes; autoconnects at boot | [D6-wifi](docs/drivers/D6-wifi.md) |
| D7 | Bluetooth (BCM4345C0) | ✅ working | scans and pairs (iPhone tested); hidden until an app opens a pairing window | [misc](docs/drivers/D1-D2-D7-D8-D9-misc.md#d7--bluetooth-) |
| D8 | Bottom button | ✅ working | generic `tap`/`double`/`hold` events for apps | [misc](docs/drivers/D1-D2-D7-D8-D9-misc.md#d8--bottom-button-) |
| D9 | Touch | ✅ n/a | there is **no** touch panel (confirmed by I²C scan) | [misc](docs/drivers/D1-D2-D7-D8-D9-misc.md) |
| D10 | Camera (OV5640) | ✅ working | format-chain fix + a **camera hub** so many apps/ML models share it at 1080p30 | [D10-camera](docs/drivers/D10-camera.md) |

**Also solved along the way:** contiguous-memory (CMA) pool resized for video/graphics, system
time/NTP, and a fully unattended cold boot (WiFi up + SSH reachable ~30–60 s after power-on, no
keyboard).

**Known rough edges / open issues:**
- 🟡 **Bluetooth** — works, but offers no profiles yet (not a speaker or headset); reconnect not tested.
- 🟡 **Harmless `caam_probe` kernel oops** on every boot (the crypto block is owned by the secure
  firmware); system runs fine. Blacklisting the `caam` module silences it.
- 🟡 **`reboot` over SSH hangs** — use `poweroff` then power-cycle. Cause not yet pinned down.
- 🟡 **Video playback on the panel** is not smooth — the hardware H.264 decoder works (~24 fps,
  low CPU) but getting decoded frames onto the display is the bottleneck. Fine as a UI device;
  not a media player. [notes](docs/developer-guide.md).

See **[docs/STATUS.md](docs/STATUS.md)** for the full table with verification notes.

---

## How it was done (the short version)

1. **Get a U-Boot prompt.** Getting bootloader/root access on a locked unit was figured out by
   **gouda-percha** (Discord) and written up here: **https://failedattempts.neocities.org/**.
   Follow that guide first. Once you can reach the `u-boot=>` prompt over the serial console (by
   interrupting the autoboot countdown), you're ready for everything in this repo.
2. **Back up the stock eMMC** (so you can always return to Android). → [docs/01-get-uboot.md](docs/01-get-uboot.md)
3. **Build the kernel** (mainline 6.18 + the patches in `kernel/`) and the **device tree**. → [docs/02-build-kernel.md](docs/02-build-kernel.md)
4. **Build a Debian rootfs** with your own WiFi and SSH baked in from a small template, so the mirror
   comes up on your network and you can SSH in headlessly. → [docs/03-build-rootfs.md](docs/03-build-rootfs.md)
5. **Flash and make it persistent** — expose the eMMC over USB from U-Boot, write the partitions from
   your PC, and save a boot script so it boots your Linux on every power-on. → [docs/04-flash-and-persist.md](docs/04-flash-and-persist.md)
6. **Pull the vendor's firmware blobs** (amp DSP tables, WiFi NVRAM) **from your own backup** — they
   aren't redistributed here. → [docs/05-extract-vendor-blobs.md](docs/05-extract-vendor-blobs.md)

Then apply the overlay in `rootfs/overlay/` (services, ALSA config, camera hub, helper scripts) and
you have the system this repo describes.

> **Your unit's details will differ from mine** — firmware builds and components change, so exact
> addresses/offsets/tables won't match. That's fine; the **logic** is what carries over: dump the
> firmware, run it through **REA / Ghidra**, figure out how the vendor's platform works, rebuild that
> on mainline, and port it. See [the reverse-engineering method](docs/00-reverse-engineering.md).

For writing apps on top (speakers, mic, camera, display, suggested gesture-UI architecture), see the
**[developer guide](docs/developer-guide.md)**.

## Shortcut: flash my prebuilt binaries

If your board is the **same revision as mine** (`cat /proc/device-tree/model` →
`lululemon Mirror V1.1`, i.MX8M Mini), you can skip building the kernel entirely and use the
known-good binaries in **[`prebuilt/`](prebuilt/)** — the exact kernel, device tree and modules
running on my unit:

| File | What |
|---|---|
| `prebuilt/Image` | the kernel (`vermagic 6.18.60-dirty`) |
| `prebuilt/imx8mm-mirror.dtb` | the device tree |
| `prebuilt/modules-6.18.60-dirty.tar.gz` | matching modules — untar into `<rootfs>/lib/modules/` |

Use `Image` + the modules **as a set** (the versions must match). You still provide the two things
that are specific to *you* and can't be shipped:
1. a **Debian rootfs** with your WiFi/SSH ([docs/03](docs/03-build-rootfs.md)), and
2. the **vendor firmware blobs** extracted from your own backup ([docs/05](docs/05-extract-vendor-blobs.md)).

Then flash per [docs/04](docs/04-flash-and-persist.md). Verify the binaries first with
`sha256sum -c prebuilt/SHA256SUMS`.

> After first boot, **change the WiFi password baked into your rootfs**, and use a non-root SSH key login (not root+password)
> (`nmcli` / `passwd` over SSH), and never share a rootfs image that still has your credentials in it.
> See [docs/03](docs/03-build-rootfs.md#after-first-boot--change-your-credentials).

> Different revision? Don't flash a mismatched dtb/kernel — build from [`kernel/`](kernel/) instead
> ([docs/02](docs/02-build-kernel.md)). If something's different on your unit, a PR or issue noting
> what matches and what doesn't is very welcome.

---

## Repo layout

```
kernel/        mainline 6.18 patches (git am), the device tree, the kernel .config,
               and the out-of-tree v4l2loopback patch (camera sharing)
prebuilt/      known-good Image + dtb + modules, to flash without building
rootfs/overlay/   files that go on top of a plain Debian rootfs (systemd units, ALSA
                  config, camera hub + helper scripts)
rootfs/templates/ WiFi / SSH / boot-script templates you populate with your details
scripts/       helper scripts (extract vendor blobs from your backup, build boot.scr, …)
docs/          the full walkthrough + per-driver deep-dives + developer guide
```

## Documentation

**Process (do these in order):**
1. [Get a U-Boot prompt + back up stock firmware](docs/01-get-uboot.md)
2. [Build the kernel, device tree, modules](docs/02-build-kernel.md)
3. [Build a Debian rootfs (headless WiFi + SSH)](docs/03-build-rootfs.md)
4. [Flash the eMMC and make it persistent](docs/04-flash-and-persist.md)
5. [Extract the vendor firmware blobs from your backup](docs/05-extract-vendor-blobs.md)

**Reference & deep-dives:**
- [Hardware reference](docs/hardware-reference.md) — chips, buses, addresses, clocks
- [How the OEM drivers were reverse-engineered & ported](docs/00-reverse-engineering.md) — the method
- [Hunting the SPL & decoding the boot chain](docs/boot-chain-anatomy.md)
- [Hardware status (D1–D10)](docs/STATUS.md)
- Drivers: [D3 display](docs/drivers/D3-display.md) · [D4 speakers](docs/drivers/D4-speakers.md) ·
  [D5 mic](docs/drivers/D5-mic.md) · [D6 WiFi](docs/drivers/D6-wifi.md) ·
  [D10 camera](docs/drivers/D10-camera.md) · [D1/D2/D7/D8/D9 misc](docs/drivers/D1-D2-D7-D8-D9-misc.md)
- [Developer guide](docs/developer-guide.md) — build apps on the mirror (audio, camera, display, UI)

## Hardware summary

| | |
|---|---|
| SoC | NXP i.MX8M Mini (MIMX8MM6), 4× Cortex-A53 @ ~1.6 GHz |
| RAM / storage | 2 GiB LPDDR4 / ~16 GiB eMMC |
| Display | 1920×1080 LVDS panel via TI SN65DSI83 (DSI→LVDS bridge), **mounted 90° — portrait device** |
| Audio out | 2× TI TAS5806 class-D amps (I²C), stereo |
| Audio in | I²S MEMS mic(s) on SAI5 |
| Camera | OmniVision OV5640, 5 MP, wide-angle, MIPI CSI-2 |
| Wireless | Broadcom/Cypress BCM4345/6 (WiFi SDIO + BT UART) |
| Input | one bottom button; **no touch screen** |

## Credits & license

- 🙏 **Huge shoutout to [gouda-percha](https://failedattempts.neocities.org/) (Discord: `gouda-percha`)**
  for cracking the bootloader/root access on the locked hardware. None of this is possible without
  that work — start there: **https://failedattempts.neocities.org/**
- Kernel patches are derivatives of the Linux kernel and are **GPL-2.0** (see `LICENSE`). Docs and
  scripts in this repo are MIT unless noted.
- Not affiliated with, or endorsed by, lululemon or NXP. "Mirror" and "lululemon" are trademarks of
  their owners; used here only to describe the hardware this project runs on.

*Contributions welcome — especially Bluetooth profiles and smooth video output.*
