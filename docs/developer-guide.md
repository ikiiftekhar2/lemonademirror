# Developer guide: building apps on the mirror

Once the system is up, the speakers, mic, camera, display, button and Bluetooth are easy to reach from an app. This is
how to use them, with the quirks that matter. Hardware details are in
[hardware-reference.md](hardware-reference.md).

## Audio out (speakers)
Play through the ALSA **`default`** device — the overlay wires it to a `dmix` so multiple apps mix:
```sh
aplay clip.wav
ffmpeg -i track.mp3 -f alsa default
```
```python
import subprocess, math, struct
rate = 48000
pcm = b''.join(struct.pack('<hh', s, s) for s in
               (int(6000*math.sin(2*math.pi*660*i/rate)) for i in range(rate)))
subprocess.run(['aplay','-q','-D','default','-t','raw','-f','S16_LE','-r',str(rate),'-c','2'],
               input=pcm, check=True)
```
- **Volume** is a hardware mixer: `amixer -c0 cset name='Master Playback Volume A' 92,92` (and `…B`).
  dB = index − 110; **max is 98 (−12 dB)** — above that the left amp over-current-trips. Default 92
  (−18 dB). `alsactl store 0` to persist.
- **First sound after boot** loses ~1.3 s while the amps load their DSP program (once per boot). Hide
  it by playing ~2 s of silence at app start.

## Audio in (mic)
Record through `default` (or the `mic` alias). Any rate; `plug` converts:
```sh
arecord -f S16_LE -r 16000 -c 1 -d 5 out.wav      # 16 kHz mono is typical for speech
```
Quiet signal, so a `+20 dB` softvol ("Mic Capture Volume") is applied. Treat it as **mono** (channel
0). Full-duplex (play + record together) works.

## Camera — shared by many apps
Open **`/dev/video10`** (not `/dev/video0`, which the hub owns). It's a normal V4L2 webcam:
**1920×1080, UYVY, 30 fps**, and any number of processes can read it at once, each getting every
frame. The format is fixed; resize/rotate/drop frames in your own process.

**Orientation:** rotate **90° CCW** for upright (`cv2.ROTATE_90_COUNTERCLOCKWISE`, ffmpeg
`transpose=2`); for a selfie view also mirror horizontally.

OpenCV (install headless in a venv to keep it small):
```python
import cv2
cap = cv2.VideoCapture("/dev/video10", cv2.CAP_V4L2)
while True:
    if not cap.grab(): break            # grab() is cheap (~1% of a core at 30 fps)
    ok, frame = cap.retrieve()          # decode only the frames you use
    if not ok: break
    small = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_LINEAR)
    upright = cv2.rotate(small, cv2.ROTATE_90_COUNTERCLOCKWISE)
    # run your model on `upright`
```
ffmpeg pipe (any language): decode + scale + rotate in ffmpeg, read fixed-size frames from stdout:
```sh
ffmpeg -f v4l2 -input_format uyvy422 -video_size 1920x1080 -i /dev/video10 \
  -vf "fps=10,scale=640:360:flags=fast_bilinear,transpose=2" -pix_fmt rgb24 -f rawvideo -
```
**CPU rules of thumb** (GC600-class board): `grab()` ≈ 1% of a core; full-1080p BGR `read()` ≈ 60%;
`cv2.resize` with `INTER_LINEAR` (2.3 ms) is ~6× cheaper than `INTER_AREA` (13.6 ms) on full frames.
Four raw readers at 30 fps cost ~5% of the board total — the *sharing* is nearly free; the cost is
what each app does with pixels. There is **no hardware video encoder**, so encoding (MJPEG/H.264) is
pure CPU.

**Exposure:** in a dim room the sensor runs at max exposure, so fast motion blurs (rolling-shutter
slant too). It doesn't affect presence/gesture models (they still get every frame); add light or cap
exposure on the `ov5640` sub-device for crisp fast motion.

## Display
- Draw to **`/dev/fb0`** (1920×1080, BGRX) or via DRM/KMS. **Use the stable device path**
  `/dev/dri/by-path/platform-32e00000.lcdif-card` — the `cardN` numbers swap between boots.
- **Rotate 90° CCW:** design portrait (1080×1920), rotate into the 1920×1080 framebuffer. The panel
  is mounted sideways.
- **Safe area:** the bezel hides the outer edge; keep content **≥20 px** from every edge (≥50 px for
  text/buttons).
- **Backlight:** `/sys/class/backlight/backlight/brightness`, 0–100, 0 = off. Boots dark; `screenon
  [N]` / `screenoff`. Independent of the display driver — draw first, then light up.
- GPU is **OpenGL ES 2.0 only** (Vivante GC600). Request GLES2 explicitly in any toolkit. Scan-out
  buffers must be **XRGB (no alpha)**.

## Bottom button
A generic input: nothing on the system reacts to it by default. Read one event per line from a socket:
```python
import socket
s = socket.socket(socket.AF_UNIX)
s.connect("/run/mirror-button/events.sock")
for line in s.makefile():
    print(line.strip())
```
| Event | When | |
|---|---|---|
| `press`, `release` | immediately | instant feedback |
| `tap` | **0.75 s after release** (ruling out a double) | main action |
| `double` | on the second release | second action |
| `hold` | **2 s into the press**, still held | deliberate action |

- **Don't hold for 5 s or more.** The hardware has its own hold-to-power-off that Linux can't change (the time is the
  reset default, not tested).
- Up to 16 clients; run as root or in group `input`. Tune with `-d` (double window) and `-H` (hold) in
  `mirror-buttond.service`. Raw input: `/dev/input/by-path/platform-30370000.snvs:snvs-powerkey-event`, `KEY_PROG1`.
- It can't wake the board from suspend, because the driver polls ([why](drivers/D1-D2-D7-D8-D9-misc.md#d8--bottom-button-)).

## Bluetooth
The mirror is **not discoverable and not pairable** by default. Pairing only happens when an app asks:

1. **Your app opens a window** when the user asks to pair: `mirror-bt-pair [seconds]` (default 120, run as root).
2. **The user picks the mirror's hostname** (`mirror` by default) in their device's Bluetooth settings and taps Pair. BlueZ
   advertises the hostname, not the `Name` set in `/etc/bluetooth/main.conf`. Tested with an iPhone.
3. **Your app shows the passkey** so the user can check it matches. The mirror's side accepts it automatically.
4. **The window closes itself.** The new device is trusted; other paired devices are disconnected and lose their trust.

The tool prints events and exits 0 when paired, 1 otherwise. `SIGTERM` cancels.
```python
import subprocess
p = subprocess.Popen(["mirror-bt-pair", "120"], stdout=subprocess.PIPE, text=True)
for line in p.stdout:
    kind, _, value = line.strip().partition(" ")
    # kind: ready | passkey (value = code to show) | paired (value = MAC + name) | timeout
ok = p.wait() == 0
```
- **Not set up yet:** the mirror offers no profiles, so it isn't a speaker or headset. Phones connect but have nothing to
  use until an app adds a service (BlueZ D-Bus, or BLE GATT for a companion app), and may drop an idle link.
- **Wi-Fi shares the radio:** pings got noticeably worse during a scan in one short test, with no loss. Avoid long scans
  during network-sensitive work.
- **Not tested:** reconnecting after a toggle or reboot, and refusing a second, untrusted device.

## Suggested architecture for a gesture-driven mirror UI
The device is well-suited to: UI screens on the panel + a camera model that detects gestures/presence
and drives the UI. This avoids the one weak spot (smooth full-motion video on the panel is slow).

```
camera → /dev/video10 ─┬─▶ gesture/presence model (own process, 10–15 fps, small frames)
                       │        │ events: swipe_left, person_present, …
                       │        ▼
                       │   UI process (KMS + OpenGL ES 2, portrait 1080×1920 rotated 90° CCW)
                       └─▶ (optional) other models
speakers/mic via ALSA default (chimes, TTS, voice)
```
- Each part is cheap: the camera hub costs ~8–10% of one core always; a 10 fps model preprocessor
  ~35–40% of a core; a swipe animation just slides already-drawn textures.
- Pick a UI toolkit with a **DRM/KMS + GLES2** backend (Qt eglfs, SDL kmsdrm, flutter-pi, or a small
  EGL/GBM app). No X11/Wayland is installed or needed.
- Pre-render screens to textures; animate by moving textures, not re-rendering per frame.

## Platform behaviour
- **Boot:** fully unattended from power — kernel + userspace reach `graphical.target` in ~8–9 s; WiFi
  up and SSH reachable ~30–60 s after power-on. Boots with the screen dark.
- **Network:** NetworkManager autoconnects WiFi (DHCP, no static IP, no mDNS — find it via your
  router). SSH: log in as a non-root sudo user with an SSH key (see docs/03); `scp -O` (no sftp subsystem).
- **Services at boot:** `screen-off` (backlight 0), `camhub` (camera), `mirror-buttond` (button events), BlueZ (hidden until an
  app pairs), ALSA restore, timesyncd (NTP; no RTC, so the clock is wrong until it syncs), NetworkManager, ssh.
- **Time:** wait for `timedatectl show -p NTPSynchronized --value` = `yes` before trusting timestamps.
- **Reboot:** `reboot` over SSH works (35–43 s). `shutdown` and `poweroff` turn the board off, and wall power brings it back. [details](drivers/reboot.md)
- **Video playback** on the panel is not smooth (HW decode works ~24 fps, but the decode→display path
  is the bottleneck). Fine as a UI device; not a media player. Measure browser or MagicMirror²-style UIs before
  committing: the GPU is GLES2-only and RAM is shared with your models (not tested).
- `/tmp` is RAM and wiped on boot.
