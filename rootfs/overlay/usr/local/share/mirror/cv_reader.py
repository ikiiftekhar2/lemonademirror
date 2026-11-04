#!/opt/mirror-cv/bin/python
"""Mirror shared-camera reader (OpenCV). Many of these can run at once.
usage: cv_reader.py full|ml SECONDS [NAME]
  full: decode every 1080p frame to BGR (e.g. tracker/recorder)
  ml:   grab every frame, decode only every 3rd -> 640x360 -> upright 360x640 (10 fps model input)"""
import sys, time, resource, cv2
mode, secs = sys.argv[1], float(sys.argv[2]); name = sys.argv[3] if len(sys.argv) > 3 else mode
cap = cv2.VideoCapture("/dev/video10", cv2.CAP_V4L2)
if not cap.isOpened():
    sys.exit(f"{name}: cannot open /dev/video10")
w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fourcc = int(cap.get(cv2.CAP_PROP_FOURCC)).to_bytes(4, "little").decode(errors="replace")
n = used = 0; shape = None; t0 = time.monotonic(); c0 = time.process_time()
while time.monotonic() - t0 < secs:
    if mode == "full":
        ok, f = cap.read()
        if not ok: break
        shape = f.shape; used += 1
    else:
        if not cap.grab(): break                       # cheap: no colour conversion
        if n % 3 == 0:
            ok, f = cap.retrieve()                     # convert only frames we use
            if not ok: break
            f = cv2.resize(f, (640, 360), interpolation=cv2.INTER_LINEAR)
            f = cv2.rotate(f, cv2.ROTATE_90_COUNTERCLOCKWISE)   # upright portrait
            shape = f.shape; used += 1
    n += 1
dt = time.monotonic() - t0; cpu = time.process_time() - c0
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
print(f"{name}: dev {w}x{h} {fourcc} | {n/dt:5.1f} fps grabbed, {used/dt:5.1f} fps used, "
      f"frame {shape} | CPU {100*cpu/dt:4.0f}% of one core | RSS {rss} MB", flush=True)
