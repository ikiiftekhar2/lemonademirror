#!/usr/bin/env python3
"""Mirror camera HTTP server: reads the SHARED camera /dev/video10 (camhub), so any number
of these servers / clients / other apps can run at the same time.
  /                         viewer page
  /stream?res=720&fps=15    MJPEG stream (multipart), upright portrait
  /snapshot.jpg?res=1080    single JPEG
  query: res = short side in px (<=1080), fps (<=30), rotate=0 for raw sensor orientation
Usage: camhttp.py PORT [default_res] [default_fps]
Encoding runs only while a client is connected (one ffmpeg per client, nice 10)."""
import os, select, subprocess, sys, socketserver, http.server, urllib.parse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
DRES = int(sys.argv[2]) if len(sys.argv) > 2 else 1080
DFPS = int(sys.argv[3]) if len(sys.argv) > 3 else 30
DEV = "/dev/video10"

def params(q):
    res = max(120, min(1080, int(q.get("res", [DRES])[0])))
    res -= res % 2
    fps = max(1, min(30, int(q.get("fps", [DFPS])[0])))
    rot = q.get("rotate", ["1"])[0] != "0"
    # fast_bilinear: 3x cheaper than default bicubic; yuvj420p: half the chroma to encode.
    # Cost is CPU-only (no HW JPEG encoder in mainline): ~80% core @480p15, ~3 cores @720p30.
    vf = (f"fps={fps},scale=-2:{res}:flags=fast_bilinear,format=yuvj420p"
          + (",transpose=2" if rot else ""))
    return res, fps, rot, vf

def ffmpeg(vf, extra):
    return ["nice", "-n", "10", "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-f", "v4l2", "-input_format", "uyvy422", "-video_size", "1920x1080", "-i", DEV, "-vf", vf, "-threads", "2", "-c:v", "mjpeg", "-q:v", "6"] + extra

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    def log_message(self, *a): pass
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        try:
            res, fps, rot, vf = params(q)
        except ValueError:
            self.send_error(400); return
        if u.path == "/":
            qs = u.query or f"res={DRES}&fps={DFPS}"
            page = (f"<!DOCTYPE html><html><head><title>Mirror Cam :{PORT}</title><style>"
                    "body{background:#111;color:#ccc;font:14px sans-serif;margin:0;display:flex;"
                    "flex-direction:column;align-items:center;height:100vh}img{max-height:92vh}"
                    f"</style></head><body><div>port {PORT} &middot; {qs}</div>"
                    f"<img src='/stream?{qs}'></body></html>").encode()
            self.send_response(200); self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(page))); self.end_headers(); self.wfile.write(page)
        elif u.path == "/snapshot.jpg":
            out = subprocess.run(ffmpeg(vf, ["-frames:v", "1", "-f", "image2", "-"]),
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
            self.send_response(200 if out else 503); self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
        elif u.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace;boundary=ffmpeg")
            self.send_header("Cache-Control", "no-cache"); self.end_headers()
            ff = subprocess.Popen(ffmpeg(vf, ["-f", "mpjpeg", "-"]),
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                while True:
                    r, _, _ = select.select([self.connection], [], [], 0)
                    if r and self.connection.recv(1, 0x40) == b"":   # MSG_DONTWAIT: client gone
                        break
                    chunk = ff.stdout.read1(65536)
                    if not chunk: break
                    self.wfile.write(chunk); self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, BlockingIOError):
                pass
            finally:
                ff.kill(); ff.wait()
        else:
            self.send_error(404)

class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True; daemon_threads = True

if __name__ == "__main__":
    print(f"camhttp: :{PORT} default res={DRES} fps={DFPS} from {DEV}", flush=True)
    S(("0.0.0.0", PORT), H).serve_forever()
