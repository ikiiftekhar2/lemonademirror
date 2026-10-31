# Contributing

PRs and issues welcome — especially:
- **Bluetooth (D7)** — the controller doesn't initialise ([notes](docs/drivers/D1-D2-D7-D8-D9-misc.md#d7-bluetooth--not-working-help-wanted)).
- **Smooth video on the panel** — HW decode works; the decode→display path is the bottleneck.
- Confirming the **front button** press (D8) on your unit.
- Other Mirror hardware revisions — report what matches and what differs.

Please don't commit real secrets (WiFi PSKs, SSH keys, tokens) or vendor/NXP/Broadcom firmware
blobs. Templates and extraction scripts only. Kernel patches should apply on the pinned mainline tag.
