#!/usr/bin/env bash
# Build boot.scr from the template for your rootfs PARTUUID.
# Usage: scripts/make-bootscr.sh <ROOTFS_PARTUUID> [out-dir]
# Needs: u-boot-tools (mkimage).
set -euo pipefail
PARTUUID="${1:?usage: make-bootscr.sh <ROOTFS_PARTUUID> [out-dir]}"
OUT="${2:-.}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
TMPL="$HERE/rootfs/templates/boot.cmd.template"
command -v mkimage >/dev/null || { echo "install u-boot-tools (mkimage)"; exit 1; }
sed "s/@@ROOTFS_PARTUUID@@/$PARTUUID/" "$TMPL" > "$OUT/boot.cmd"
mkimage -A arm64 -O linux -T script -C none -a 0x40800000 -n "LemonadeMirror boot" \
        -d "$OUT/boot.cmd" "$OUT/boot.scr"
echo "wrote $OUT/boot.scr (PARTUUID=$PARTUUID)"
