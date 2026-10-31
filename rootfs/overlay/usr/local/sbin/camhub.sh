#!/bin/sh
# Mirror camera hub (2026-10-31): sole owner of the sensor (/dev/video0).
# Sets ov5640 -> csis -> csi to 1920x1080 UYVY @30 and copies frames 1:1 (no conversion,
# ~8% of one core with the cached-buffer imx7-media-csi patch) into the shared virtual
# camera /dev/video10 (v4l2loopback), which any number of apps can read at once.
RES=${CAMHUB_RES:-1920x1080}; FPS=${CAMHUB_FPS:-30}; M=/dev/media0; OUT=/dev/video10
i=0; until media-ctl -d $M -p 2>/dev/null | grep -q 'entity.*ov5640' && [ -e $OUT ]; do
  i=$((i+1)); [ $i -gt 60 ] && { echo "camhub: camera graph or $OUT missing"; exit 1; }; sleep 1; done
sleep 1
for try in 1 2 3 4 5; do
  /usr/local/sbin/camset.sh $RES $FPS >/dev/null 2>&1
  media-ctl -d $M -p | grep -q '"csis-32e30000.mipi-csi":0 \[ENABLED' && break
  echo "camhub: link not enabled yet (try $try)"; sleep 2
done
exec ffmpeg -nostdin -hide_banner -loglevel error -f v4l2 -input_format uyvy422 \
  -video_size $RES -framerate $FPS -i /dev/video0 -c:v copy -f v4l2 $OUT
