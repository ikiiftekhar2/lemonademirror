# How the OEM drivers were reverse-engineered and ported to mainline Linux

The Mirror shipped with **Android 10 + an NXP "kernel_imx" 5.4 vendor kernel**. All the interesting
peripheral drivers (amps, mic machine driver, camera, the DSI→LVDS bridge config) lived either as
**built-in drivers compiled into that vendor kernel** or as **data inside the vendor device-tree
overlays**. None of it is in mainline Linux in the exact form this board needs.

**For the most part, this one methodology carried the whole port** — the loop below is what got
display, audio, mic and camera working. A lot of the reverse-engineering legwork (loading the vendor
kernel, cross-referencing symbols, pulling data out of the binary, diffing versions) was done with
the **REA — *reverse-engineer-anything* — toolkit** (on GitHub; see Credits in the
[README](../README.md)), alongside plain `objdump`, `dtc` and Ghidra.

The porting method was always the same loop:

1. **Dump the stock firmware** off the mirror (eMMC image + the `boot_a` / `dtbo_a` partitions).
2. **Extract** the vendor Android **kernel ELF** and the **device-tree overlays** from those dumps.
3. **Reverse-engineer** the specific peripheral: read the vendor driver's machine code (Ghidra +
   `objdump`) and/or decode the vendor device tree, down to exact register values and GPIO polarities.
4. **Map** each vendor behaviour onto the closest **mainline Linux driver**, and write a small patch
   (or a device-tree property, or a firmware blob) to make mainline behave the same way.
5. **Deploy over the serial console + USB**, boot, and verify on the real hardware — then iterate.

This doc covers steps 1–4 as a general recipe. The per-driver pages
([D3 display](drivers/D3-display.md), [D4 speakers](drivers/D4-speakers.md),
[D10 camera](drivers/D10-camera.md), …) show how it played out for each block.

---

## 1. Dumping the stock firmware

Getting bootloader/root access to a locked unit is the external part — see
[01-get-uboot.md](01-get-uboot.md) (credit: **gouda-percha**). Once you have a root ADB shell (via
that guide) and/or a U-Boot prompt over the UART, you can read the raw eMMC and the individual boot
partitions:

```sh
# from a root adb shell on the stock Android system:
adb exec-out "dd if=/dev/block/mmcblk2      bs=4M" > mmcblk2.img        # whole eMMC (~16 GiB)
adb exec-out "dd if=/dev/block/by-name/boot_a  bs=1M" > boot_a.img      # Android boot image (kernel+ramdisk)
adb exec-out "dd if=/dev/block/by-name/dtbo_a  bs=1M" > dtbo_a.img      # device-tree overlays
adb exec-out "dd if=/dev/block/by-name/vendor_a bs=1M" > vendor_a.img   # vendor partition (HALs, configs, firmware)
```

**Keep `mmcblk2.img` forever** — it's your one-command route back to a 100% stock mirror
(`dd` it back), and it's the source for the vendor firmware blobs this project needs
([05-extract-vendor-blobs.md](05-extract-vendor-blobs.md)). The serial console (UART, 115200 8N1) is
how you drive U-Boot and watch the kernel boot throughout; large data dumps go over the much faster
USB (ADB / USB mass-storage), not the UART itself.

> On this hardware the eMMC is also exposable directly from U-Boot with `ums 0 mmc 2` (USB Mass
> Storage), which turns the eMMC into a USB disk on your PC — used later for flashing. Same idea for
> reading individual partitions out.

## 2. Extracting the analysis targets

**The vendor kernel ELF.** Android boot images wrap the kernel. Unpack `boot_a.img` (e.g. with
`unpack_bootimg` / `abootimg`) to get the compressed `Image`, decompress it, and — crucially — this
vendor kernel is **unstripped and ships a full `kallsyms` table**. That means every function and
every global data symbol has a name and an address. Reconstruct an ELF (or just work on the raw
`Image` with the kallsyms offsets) and you can navigate it like a map:

```
tas5806_probe            @ 0xffff800010f99c6c
tas5806_init_dsp_work    @ 0xffff800010f9a414
imx_hifi_hw_params       @ 0xffff800010fc2f64
fsl_sai_set_dai_fmt      @ 0xffff800010fb0ae8
registers_tweeters       @ 0xffff800011e5b9d8   (global, 3264 bytes)
registers_woofers        @ 0xffff800011e5c698   (global, 3264 bytes)
...
```

**The device-tree overlays.** Decompile `dtbo_a.img` with `dtc -I dtb -O dts` to get readable device
trees. These carry the vendor's exact hardware wiring: which GPIO is a reset vs power-down and its
**active polarity**, clock parents and rates, I²C addresses, pin-mux settings, and sometimes whole
register tables (the DSI→LVDS bridge config lived here, not in code).

## 3. Reverse-engineering a peripheral

Two complementary sources, used per peripheral:

### 3a. Reading the vendor driver's machine code (Ghidra + objdump)

Load the vendor kernel into the **REA** (*reverse-engineer-anything*) toolkit or **Ghidra** (headless
or GUI) for AArch64, or disassemble a symbol range directly with `objdump`:

```sh
aarch64-linux-gnu-objdump -d --start-address=0x.. --stop-address=0x.. vendor_vmlinux.elf
```

> Practical note: on the machine used here, Ghidra's AArch64 **decompiler** native component wasn't
> available, so the primary tool ended up being **`objdump -d` plus the kallsyms table** — reading
> the disassembly function by function. Ghidra headless still helped for cross-references and
> navigating. Either way the goal is the same: understand exactly what the driver does.

What you're looking for in each probe/hw_params/init function:
- the **sequence of register writes** (and their values) that bring the device up;
- **GPIO** requests and the value written (→ active-high vs active-low);
- **clock** get/set calls and rates;
- **format/slot** configuration for audio (I²S vs TDM, slot count, slot width);
- pointers to **static data tables** (see next).

### 3b. Pulling static data tables out of the ELF

Vendor drivers often ship big constant tables — e.g. the TAS5806 amps' entire "DSP program" is **two
3264-byte `{register, value}` tables compiled into the kernel** (`registers_tweeters`,
`registers_woofers`), not a separate firmware file. Because the symbols are named and the ELF has
`PT_LOAD` segments, you can pull the exact bytes at a symbol's address:

```python
# pseudo: find the PT_LOAD segment containing the symbol's virtual address, read N bytes
seg = [p for p in load_segments if p.vaddr <= sym_addr < p.vaddr + p.memsz][0]
data = elf[seg.offset + (sym_addr - seg.vaddr) : ...][:3264]
```

Then decode the table's opcodes (for the amps: plain `{reg,val}` pairs, with a couple of meta-opcodes
like "delay N ms" and "skip"). You now have a byte-exact copy of the OEM's device programming, which
you can ship as a firmware file for the mainline driver to replay. (SHA-256 the extracted bytes and
compare against the ELF so you know they're exact.)

### 3c. Decoding the device tree

For hardware wiring, `dtc`-decompile the overlay and resolve phandles. This is where the DSI→LVDS
**bridge register table**, the camera's MCLK topology, the SAI (audio) clock parents and the amp GPIO
polarities all came from. Comparing the vendor DT against your mainline DT, property by property, is
often the fastest way to find "the one thing that's different".

## 4. Mapping onto mainline

For each block, find the mainline driver that targets the same IP and make it match the vendor:

| Vendor (Android 5.4 kernel) | Mainline 6.18 equivalent | What the port needed |
|---|---|---|
| built-in `snd_soc_tas5806` + machine driver | `sound/soc/codecs/tas5805m.c` + `imx-card` + `fsl_sai` | ship vendor DSP tables as firmware; small driver fixes; SAI clock + TDM device-tree |
| DSI→LVDS bridge config in dtbo | `drivers/gpu/drm/bridge/ti-sn65dsi83.c` | patch to write the vendor's LVDS-stage registers |
| `mxc_mipi_csi` / `mx6s_capture` + `ov5640_mipi` | `imx7-media-csi` + `imx-mipi-csis` + `ov5640` | format-chain config; cached buffers; a sharing layer |
| vendor SAI5 DMIC machine driver | `fsl_sai` + `dmic-codec` via `imx-card` | one device-tree property (MCLK direction) |

The result is a handful of **kernel patches** (`kernel/patches/`), a **device tree**
(`kernel/imx8mm-mirror.dts`), some **firmware blobs extracted from your own backup**, and a
**rootfs overlay** (services + config). None of it reships NXP's or the vendor's binaries.

## 5. The deploy/verify loop

Each change was a module-only rebuild (to keep the kernel's `vermagic` matching, so modules load
without reflashing the whole kernel), copied to the board over SSH or the UART-exposed USB disk, then
reloaded and tested on the glass / by ear / with `v4l2-ctl`. See
[04-flash-and-persist.md](04-flash-and-persist.md) for the mechanics and the "don't `make
olddefconfig`" footgun that bricked a couple of boots.
