# Prebuilt binaries

Known-good build from the reference unit, for skipping the kernel build if your board is the same
revision. Verify with `sha256sum -c SHA256SUMS`.

| File | What |
|---|---|
| `Image` | mainline 6.18.60 kernel with the LemonadeMirror patches, `vermagic` **`6.18.60-dirty`** |
| `imx8mm-mirror.dtb` | the device tree (display override, audio clocks, mic MCLK, CMA, etc.) |
| `modules-6.18.60-dirty.tar.gz` | matching module tree — untar into your rootfs: `tar xzf … -C <rootfs>/lib/modules/` |
| `v4l2loopback.ko` | patched multi-reader v4l2loopback (also inside the modules tarball) |

**Use `Image` and the modules as a set** — the module `vermagic` must match the kernel, or modules
won't load.

**Still required separately** (not here, by design):
- the vendor firmware blobs — extract from your own backup ([docs/05-extract-vendor-blobs.md](../docs/05-extract-vendor-blobs.md));
- `boot.scr` — build it for your rootfs PARTUUID ([docs/04-flash-and-persist.md](../docs/04-flash-and-persist.md)).

These are GPL-2.0 binaries; full source is the upstream Linux 6.18.60 tree plus
[`kernel/patches/`](../kernel/patches/) and [`kernel/kernel.config`](../kernel/kernel.config).
