# D5 — Microphone: one device-tree property

**Status: ✅ working.** Record + playback confirmed. Part of patch `0004`.

## Hardware
I²S MEMS microphone(s) on **SAI5** (the SAI is the clock master), 48 kHz, 32-bit slots. Exposed to
userspace through a generic `dmic-codec` wired into the `imx-card` machine driver, as capture device
`hw:0,1` on the same sound card as the speakers. **Mainline drivers:** `fsl_sai` + `snd-soc-dmic`.

## The problem
`arecord` opened the stream but the first read failed with **EIO** within ~0.5 s. The clocks looked
configured and there were no kernel errors.

## Diagnosis
Capturing the SAI5 registers *while the stream was RUNNING* (via regmap debugfs, and confirmed by
live register pokes through `/dev/mem`) showed the receiver was set up correctly but **never saw a
frame sync** — the RX bit-clock generator wasn't running. The giveaway: switching the SAI's clock
source to the internal bus clock made it start immediately, so the problem was the **MCLK direction**.

On this SAI version, with `MCR.MOE = 0` the SAI takes MCLK from the (undriven) SAI5_MCLK **pad**
instead of generating it, so nothing clocks. SAI1 (speakers) already had the property that sets
`MOE = 1`; SAI5 didn't.

## The fix
Add one property to the `&sai5` node in the device tree:

```dts
&sai5 {
    ...
    fsl,sai-mclk-direction-output;   /* MCR.MOE = 1: drive MCLK, don't wait for it */
};
```

Rebuild the `.dtb`, deploy, cold-boot — capture works with no code changes. (How it was proven before
committing: poking `MCR` bit 30 live via `/dev/mem` while a capture ran made frames flow and recorded
clean voice.)

## Using it
Record through the ALSA `default` device (or the `mic` alias). It's quiet, so the overlay adds a
`softvol` "Mic Capture Volume" (+20 dB default). Treat it as mono (channel 0). Full-duplex (play +
record at once) works. See the [developer guide](../developer-guide.md).
