# D3 — Display: the DSI→LVDS bridge, the driver we used, and the port from Android

**Status: ✅ working.** Panel locks and shows a stable image; content is upright; colours correct.
Patches: [`kernel/patches/0001-D3-FIX-ti-sn65dsi83-vendor-LVDS-output-stage-overrid.patch`](../../kernel/patches/0001-D3-FIX-ti-sn65dsi83-vendor-LVDS-output-stage-overrid.patch)
and [`0002-D3-followup-FRAMEBUFFER_CONSOLE_ROTATION...patch`](../../kernel/patches/0002-D3-followup-FRAMEBUFFER_CONSOLE_ROTATION-y-LOCALVERS.patch).

## The display pipeline

```
i.MX8MM LCDIF  ──MIPI-DSI──▶  TI SN65DSI83  ──LVDS──▶  1920×1080 panel (tn,hj070na)
  (mxsfb DRM)                 (DSI→LVDS bridge,                 landscape glass,
                              I²C2 @0x2c)                       mounted 90° CW in a
                                                                portrait body
                              + pwm-backlight (PWM, 0–100)
```

**The drivers we use (all mainline Linux 6.18):**
- Display controller: **`mxsfb`** DRM driver (`drivers/gpu/drm/mxsfb/`) for the i.MX8MM LCDIF.
- Bridge: **`ti-sn65dsi83`** (`drivers/gpu/drm/bridge/ti-sn65dsi83.c`) — this is the driver we
  patched. (The vendor DT calls the chip "SN65DSI84"; the SN65DSI83 driver drives it correctly.)
- Panel: **`panel-lvds`** (`panel-simple`-style) with the panel's timings in the device tree.
- Backlight: **`pwm-bl`** (`pwm-backlight`).

The GPU (**Vivante GC600**, `etnaviv`) is separate and only needed for accelerated rendering
(OpenGL ES 2).

## The problem

On Android the panel worked. On mainline, the whole DRM stack came up clean — `mxsfb` initialised,
the connector reported connected at 1920×1080@60 — but **the panel never showed a real image**. It
sat in its own power-on "RGBWB" colour-cycling self-test pattern, which means **the LVDS link never
locked**: the bridge wasn't producing a valid LVDS signal the panel accepted.

(Early on this looked like a *success* — "the panel is lighting up / cycling colours!" — but that
cycling pattern is exactly what the panel shows when it gets **no** valid signal. Worth knowing so
you don't chase the wrong thing.)

## Root cause

The **mainline `ti-sn65dsi83` driver derives the bridge's LVDS output-stage registers from the panel
timings**, using generic formulas. For this specific panel those derived values are wrong, so the
bridge's internal LVDS PLL never locks.

The OEM didn't use generic formulas — it programmed a **fixed, panel-specific register table** into
the bridge. That table wasn't in driver code; it lived in the vendor **device-tree overlay** as a
45-entry `{register, value}` list for the SN65DSI8x.

### How the vendor values were recovered (the RE step)

This is the [general method](../00-reverse-engineering.md) applied to the display:

1. From the eMMC dump, pull `dtbo_a.img` (the vendor device-tree overlays) and decompile it:
   `dtc -I dtb -O dts dtbo_a.img > dtbo_a.dts`.
2. In the decoded DT, find the bridge node and its **register init table** (here: an
   `sn65dsi84,addresses` / `...,values` pair, ~43–45 registers).
3. Dump the **live** bridge registers on our mainline boot via regmap debugfs
   (`/sys/kernel/debug/regmap/<i2c>/registers`) and **diff** them against the vendor table.

The diff pointed straight at the LVDS output-stage registers. The mainline-derived values disagreed
with the vendor at (hex register : mainline → vendor):

```
0x0B : 0x10 → 0x28      0x30 : 0x0F → 0x19
0x18 : 0x78 → 0x6C      0x34 : 0x50 → 0x19
0x2C : 0x00 → 0x64      0x36 : 0x00 → 0x14
                        0x38 : 0x00 → 0x14
```

The DSI-side registers already matched, so only the LVDS output stage needed correcting.

> For peripherals whose config lives in **driver code** rather than the device tree (the amps, the
> camera), the same diff is done against the disassembly of the vendor kernel ELF with Ghidra /
> `objdump` — see [D4](D4-speakers.md) and [D10](D10-camera.md). For the bridge, the device-tree
> overlay had everything.

## The fix — a small driver patch

Patch `0001` adds an **opt-in device-tree flag** and, when set, writes the vendor's LVDS-stage values
at the right moment in the bridge's enable sequence:

- New boolean DT property **`ti,lvds-vendor-override`** on the bridge node (also added to the YAML
  binding, which has `additionalProperties: false`).
- When present, the driver applies this `reg_sequence` **inside `sn65dsi83_atomic_pre_enable`, just
  before the PLL-enable (`REG_RC_PLL_EN`, 0x0d) and soft-reset writes** — so the override lands after
  the driver's own setup but before the PLL is told to lock:

  ```
  0x0b=0x28  0x18=0x6c  0x2c=0x64  0x30=0x19  0x34=0x19  0x36=0x14  0x38=0x14  0x3a=0x14
  ```

  (All of these are already in the driver's writeable register ranges, so no regmap changes.)

Build it as a module against mainline 6.18 (`make M=drivers/gpu/drm/bridge`), deploy, and on the next
modeset the kernel log prints `vendor LVDS override applied (9 regs)`, a regmap dump matches the
vendor values, bridge register 0x0a reads with bit 7 set (**PLL locked**), and real pixels appear on
the glass.

## Orientation — the panel is mounted sideways

The panel is a **1920×1080 landscape** LCD physically mounted **90° clockwise** inside the portrait
mirror body (the OEM's Android rotated everything in software to match). So "native" framebuffer
output appears rotated on the glass.

Finding the right direction took an edge test: draw a marker on the framebuffer's **left** edge and
it appears on the physical **top** → the glass shows the framebuffer rotated 90° CW → content must be
**pre-rotated 90° CCW**.

Two layers handle it:
- **Console / anything using the kernel framebuffer:** add `fbcon=rotate:3` (90° CCW) to the kernel
  command line **and** make sure the kernel is built with **`CONFIG_FRAMEBUFFER_CONSOLE_ROTATION=y`**
  (patch `0002`). This was the subtle one: without that config symbol, `fbcon=rotate:N` is **silently
  ignored** — two full reflash-and-reboot cycles looked identical before this was spotted.
- **Apps:** rotate content 90° CCW at render time (design your UI as 1080×1920 portrait and rotate
  into the 1920×1080 framebuffer). See the [developer guide](../developer-guide.md).

## Backlight (D3b)

`pwm-backlight`, `/sys/class/backlight/backlight/brightness`, **0–100**, where **0 fully disables the
PWM** (truly dark, not dim). It is **independent of the display driver**: a full DRM modeset with
brightness at 0 leaves it at 0 (verified), so you can draw first and light the panel afterward to
avoid flashes. The system boots dark on purpose via a `screen-off` service; `screenon [N]` /
`screenoff` helper scripts are in the [overlay](../../rootfs/overlay/usr/local/bin/).

## Build footguns (learned the hard way)

- **Never `make olddefconfig`** after toggling a config symbol on this tree — it regenerated the
  config and produced a kernel that hung right after `Starting kernel ...` (bricked two boots).
  Start from the known-good `.config`, flip only the one symbol, rebuild. A resulting `Image` whose
  size is very different from your last good one is a red flag.
- Keep the kernel **`vermagic`** stable so you can hot-swap modules without reflashing the whole
  kernel: `CONFIG_LOCALVERSION="-dirty"`, `CONFIG_LOCALVERSION_AUTO=n`, and build with
  `LOCALVERSION= make …` (a git commit otherwise shifts the version string).
- Recovery from a bad kernel: interrupt U-Boot over the UART, `ums 0 mmc 2` to expose the eMMC as a
  USB disk, mount the FAT boot partition on your PC, copy a known-good `Image` back. See
  [04-flash-and-persist.md](../04-flash-and-persist.md).

## Vendor audit: clock range and panel mode (patch `0008`)
A later decode of the vendor kernel showed two more differences, now fixed:
- **`0x0a` = `0x05`** joined the override. It still claimed a 137.5–154 MHz LVDS clock while the bridge output 74.25 MHz per channel:
  this panel is **dual-link**, but the driver treats the link as single and the override only partly converts it.
- **Panel mode:** hsync 80, back porch 120, 941×529 mm. The vendor kernel looks for `panel-timing`, but its DT only has
  `display-timings`, so those DT numbers never ran on Android; a compiled-in mode did.

**Result on the reference unit:** the bridge's silent `PLL_UNLOCK` flag (`0xe5` bit 0) went from 20 events in 10 minutes to 0, with the
picture verified by eye. It doesn't change video frame pacing, which is a rendering limit, not a link problem.

Still different from vendor, with no symptom: burst DSI vs non-burst sync pulse, and D-PHY timing from upstream's formula.
