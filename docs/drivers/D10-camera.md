# D10 — Camera: format chain, cached buffers, and a sharing hub

**Status: ✅ working.** 1920×1080 @30 fps, and **any number of apps / ML models can read it at the
same time**. Patches `0005` and `0006`, plus the out-of-tree `v4l2loopback` patch.

## Hardware
**OmniVision OV5640** (5 MP, wide-angle), I²C3 @0x3c, over **MIPI CSI-2 (2 lanes)**, MCLK 24 MHz.
Pipeline: sensor → **`imx-mipi-csis`** (CSIS receiver) → **`imx7-media-csi`** (CSI bridge) →
`/dev/video0`. All mainline drivers; the OEM used NXP's `mx6s_capture` / `mxc_mipi_csi` instead.

## Fix 1 — the format chain (-EPIPE on STREAMON)
Streaming failed with `-EPIPE`. Cause: in CSI-2 mode the OV5640 only offers the **`UYVY8_1X16`**
media-bus format; a mismatched format request silently became JPEG, and the CSIS→CSI link failed
validation. Fix: set every pad in the pipeline to `UYVY8_1X16` with `media-ctl`, then
`v4l2-ctl --set-fmt-video=…,pixelformat=UYVY`. The [overlay](../../rootfs/overlay/usr/local/sbin/camset.sh)
(`camset.sh`) does this at boot.

## Fix 2 — cacheable capture buffers (patch `0005`)
A 1:1 copy of 1080p30 pinned a whole CPU core and only reached 15 fps. The CSI driver allocated
**coherent** DMA buffers, which are mapped **uncached** on i.MX8MM, so every CPU read of a frame
crawled. Patch: opt the capture queue into **non-coherent (cacheable)** buffers
(`vq->non_coherent_mem = 1` in `queue_setup`); vb2 still does the cache syncs. Result: the same copy
now costs ~8–10% of **one** core at 30 fps.

## Fix 3 — memory pool (patch `0006`)
Video/graphics output needs contiguous (CMA) memory and the default pool (32 MiB) was too small. The
device-tree `reserved-memory` node was **missing the mandatory empty `ranges;`**, so the kernel
**silently ignored the whole node** — including the CMA sizing *and* the secure-firmware (OP-TEE)
reservations. Adding `ranges;` makes a 128 MiB CMA pool live (and properly reserves OP-TEE/rpmsg).
The camera driver is also capped to 32 MiB of buffers so it can't starve the display.

## Fix 4 — sharing (the camera hub)
A V4L2 sensor can only be streamed by **one** process. To let several apps + ML models use the camera
at once, the overlay runs a **hub**:

```
OV5640 → /dev/video0 ──[camhub: ffmpeg 1:1 copy, ~8–10% of one core]──▶ /dev/video10  (v4l2loopback)
          (owned by camhub,                                              │  │  │
           never opened directly)                        app ── OpenCV ─┘  │  │
                                                         ML model ─────────┘  │
                                                         preview / recorder ──┘
```

- **`camhub.service`** owns `/dev/video0`, sets it to 1080p30 UYVY, and copies frames into
  **`/dev/video10`**, a `v4l2loopback` virtual camera.
- **`v4l2loopback` needs a patch** for this: the packaged versions allow only one reader. The repo's
  [`kernel/v4l2loopback-0.13.2-mirror.patch`](../../kernel/v4l2loopback-0.13.2-mirror.patch) makes it
  allow **many** concurrent streaming readers (multi-reader STREAMON, format-adjust instead of EBUSY,
  shared buffer ring, atomic mmap refcount) and builds against kernel 6.18.
- Every app just opens `/dev/video10` like a normal webcam. Measured: 4 raw readers at 30 fps each for
  ~5% total CPU; 6 mixed consumers (incl. 2 OpenCV models) all served at once.

## Orientation & exposure
Raw frames are **sideways**: rotate **90° CCW** for upright (`transpose=2` in ffmpeg,
`cv2.ROTATE_90_COUNTERCLOCKWISE`). In a dim room the sensor runs at max exposure, so fast motion
**blurs** (plus rolling-shutter slant) — that's the camera, not the pipeline, and it doesn't affect
presence/gesture models (which get every frame at 30 fps). See the [developer guide](../developer-guide.md)
for OpenCV/ffmpeg recipes and CPU rules of thumb.
