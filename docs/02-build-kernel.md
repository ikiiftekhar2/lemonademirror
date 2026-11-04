# 2. Build the kernel, device tree and modules

Mainline **Linux 6.18.60** + the patches in [`kernel/patches/`](../kernel/patches/). Cross-compile on
any x86/ARM Linux box with an `aarch64` toolchain (the real unit's builds were done on a separate
build machine, not the mirror).

## Toolchain
```sh
sudo apt install gcc-aarch64-linux-gnu bc bison flex libssl-dev make device-tree-compiler
```

## Get the source and apply the patches
```sh
git clone --depth 1 -b v6.18.60 \
  https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git linux
cd linux
git am /path/to/lemonademirror/kernel/patches/*.patch
```
The eight patches: `0001` display bridge override, `0002` console rotation config, `0003`+`0004` audio
(SAI clocks, amp driver, mic MCLK), `0005` camera cached buffers + CMA node, `0006` reserved-memory
`ranges;` + camera memory cap, `0007` Bluetooth fixes + bottom button (polling `snvs_pwrkey`), `0008` bridge clock range + panel mode. They also add the device tree
`arch/arm64/boot/dts/freescale/imx8mm-mirror.dts` (a copy is in [`kernel/`](../kernel/imx8mm-mirror.dts)
for reference).

## Configure
Use the provided config (it has the display-console-rotation and vermagic settings already):
```sh
cp /path/to/lemonademirror/kernel/kernel.config .config
make ARCH=arm64 olddefconfig   # OK on a *fresh* tree; see the footgun note below
```

> ⚠️ **Footgun:** don't run `make olddefconfig` *after* hand-toggling a symbol on an already-built
> tree — on this tree it regenerated the config into a kernel that hung at `Starting kernel ...`.
> Start from `kernel.config`, change only what you mean to, and keep a known-good `.config`.

Keep the module `vermagic` stable so you can hot-swap individual modules without reflashing the whole
kernel. The config sets `CONFIG_LOCALVERSION="-dirty"` and `CONFIG_LOCALVERSION_AUTO=n`; always build
with `LOCALVERSION=` in the environment:

## Build
```sh
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
LOCALVERSION= make -j$(nproc) Image modules freescale/imx8mm-mirror.dtb
```
Outputs:
- `arch/arm64/boot/Image`
- `arch/arm64/boot/dts/freescale/imx8mm-mirror.dtb`
- modules under the tree (install with `make modules_install INSTALL_MOD_PATH=…` into your rootfs)

Your `uname -r` / module dir will be **`6.18.60-dirty`**. Note this — it must match between the
`Image` and the modules you install, or modules won't load.

## v4l2loopback (camera sharing)
Built out-of-tree against the same kernel, with the repo's patch:
```sh
git clone -b v0.13.2 https://github.com/v4l2loopback/v4l2loopback.git
cd v4l2loopback
git apply /path/to/lemonademirror/kernel/v4l2loopback-0.13.2-mirror.patch
LOCALVERSION= make -C /path/to/linux M=$PWD modules
# install v4l2loopback.ko into /lib/modules/6.18.60-dirty/extra/ in your rootfs
```

Next: [build the rootfs](03-build-rootfs.md).
