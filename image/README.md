# LemonadeMirror image

An optional one-script install on top of the [kernel package](../README.md#the-kernel-package). **To burn it, follow the [full guide](../docs/06-flash-image.md).** Tested on real hardware: a second Mirror V1.1 flashed from macOS passed all 20 hardware checks. Download it from the [latest release](https://github.com/ikiiftekhar2/lemonademirror/releases/latest).

| File | Purpose |
|---|---|
| `flash-mirror.sh`, `flash-mirror.py` | Burn the image onto a Mirror V1.1 in U-Boot USB mode |
| `uart-check.py` | Optional board check before flashing |
| `build-image.sh`, `packages.txt` | Build the image from scratch |
