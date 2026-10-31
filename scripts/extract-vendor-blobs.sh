#!/usr/bin/env bash
# Extract the TAS5806 amp DSP register tables from YOUR vendor kernel.
#
# These two 3264-byte {reg,val} tables are compiled into the stock Android kernel
# as the symbols registers_tweeters / registers_woofers. This script reads them
# out of an UNSTRIPPED vendor vmlinux ELF (with a symbol table) and writes the
# firmware files the mainline tas5805m driver loads.
#
# Getting a vmlinux ELF from boot_a.img:
#   1) unpack the Android boot image (e.g. `unpack_bootimg --boot_img boot_a.img`)
#   2) decompress the kernel payload (gunzip/lz4/xz depending on the image)
#   3) reconstruct an ELF with symbols from the built-in kallsyms, e.g.
#        https://github.com/marin-m/vmlinux-to-elf
#      -> vmlinux  (has registers_tweeters / registers_woofers as symbols)
#
# Usage: scripts/extract-vendor-blobs.sh <vmlinux-elf> <out-dir>
set -euo pipefail
VMLINUX="${1:?usage: extract-vendor-blobs.sh <vmlinux-elf> <out-dir>}"
OUT="${2:?usage: extract-vendor-blobs.sh <vmlinux-elf> <out-dir>}"
mkdir -p "$OUT"
python3 "$(dirname "$0")/_extract_amp_tables.py" "$VMLINUX" \
        registers_tweeters:"$OUT/tas5805m_dsp_tweeters.bin" \
        registers_woofers:"$OUT/tas5805m_dsp_woofers.bin"
