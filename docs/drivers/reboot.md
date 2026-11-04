# Reboot and power-off

`reboot`, `systemctl reboot` and `shutdown -r now`, with or without `sudo`, work over SSH: 8 of 8 came back in 35–43 s on the reference unit.
`shutdown now` powers off and stays off; wall power brings it back (a button tap doesn't). `poweroff` uses the same path, though it wasn't run separately.

## What was wrong
A plain `reboot` never came back, and earlier notes guessed it parked in U-Boot. What testing showed:
- Userspace shuts down cleanly in about 2.5 s; the hang is in the kernel's last step.
- A direct PSCI `SYSTEM_RESET` from a running system came back in 35 s.
- A higher-priority restart handler making the same call, on a normal reboot, still hung. So it isn't just `pca9450`'s restart handler (priority 130) beating PSCI (129); the hang comes before restart handlers.
- A hung reboot recovered by itself when systemd's 10-minute hardware watchdog expired, so the reset hardware is fine.

**The driver responsible isn't identified.** `device_shutdown()` is the likely spot, as the working path skips it. A kernel log that survives the hang (UART or pstore) would settle it. PRs welcome.

## The fix
No kernel or boot-partition change. From `rootfs/overlay/`:
- `usr/lib/systemd/system-shutdown/mirror-reboot`: runs after services stop and disks are unmounted, then goes straight to the firmware.
- `usr/local/lib/mirror-reboot/mirror_reset_now.ko`: makes the PSCI call when loaded (`off=1` powers off). Built for vermagic `6.18.60-dirty`; source and Makefile in [`tools/mirror-reboot/`](../../tools/mirror-reboot/).
- `etc/systemd/system.conf.d/mirror-reboot.conf`: `RebootWatchdogSec=60s`, so a stuck reboot should recover in about a minute (the 60 s value hasn't been needed yet).

`reboot`, `shutdown` and `poweroff` are all links to `systemctl`, so they all reach the hook. `reboot -f` skips systemd and isn't covered.

**To undo:** remove those files, then `systemctl daemon-reexec`.
