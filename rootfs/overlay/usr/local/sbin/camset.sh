#!/bin/sh
# camset.sh WIDTHxHEIGHT FPS  - set ov5640 -> csis -> csi -> video0 chain (UYVY8_1X16)
R=${1:-2592x1944}; F=${2:-15}; M=/dev/media0
media-ctl -d $M -l '"ov5640 2-003c":0 -> "csis-32e30000.mipi-csi":0 [1]'
media-ctl -d $M -V "\"ov5640 2-003c\":0 [fmt:UYVY8_1X16/$R@1/$F]"
for p in '"csis-32e30000.mipi-csi":0' '"csis-32e30000.mipi-csi":1' '"csi":0' '"csi":1'; do media-ctl -d $M -V "$p [fmt:UYVY8_1X16/$R]"; done
v4l2-ctl -d /dev/video0 --set-fmt-video=width=${R%x*},height=${R#*x},pixelformat=UYVY
