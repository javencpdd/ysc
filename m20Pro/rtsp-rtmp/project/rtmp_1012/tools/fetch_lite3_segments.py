#!/usr/bin/env python3
# fetch_lite3_segments.py — 从 PC 下载 Lite3 HLS fMP4 分片（约 20s），供 M20 ffprobe 同方法分析
# PTS 是编码时间戳，传输快慢不影响帧间隔分析结果
import urllib.request, re, sys, os

BASE = "http://192.168.2.1:8888/test/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lite3_segments.mp4")
TARGET_SEGS = 20

def get(url, timeout=6):
    return urllib.request.urlopen(url, timeout=timeout).read()

# 1. master -> media playlist
master = get(BASE + "index.m3u8").decode("utf-8", "replace")
m = re.search(r'^(stream\.m3u8.*)$', master, re.M)
if not m:
    print("no media playlist in master:", master[:200]); sys.exit(1)
media_url = BASE + m.group(1).strip()

# 2. media playlist -> init map + segment list
media = get(media_url).decode("utf-8", "replace")
mi = re.search(r'#EXT-X-MAP:URI="([^"]+)"', media)
init_name = mi.group(1) if mi else None
segs = re.findall(r'^(?!#)(\S+\.(?:ts|m4s|mp4))\s*$', media, re.M)
if not segs:
    print("no segments in:", media[:300]); sys.exit(1)
segs = segs[:TARGET_SEGS]
print("media=%s init=%s segments=%d" % (media_url, init_name, len(segs)))

# 3. download: init first, then segments
total = 0
with open(OUT, "wb") as fh:
    if init_name:
        data = get(media_url.rsplit("/", 1)[0] + "/" + init_name)
        fh.write(data); total += len(data)
        print("init %s: %d bytes" % (init_name, len(data)))
    for s in segs:
        data = get(media_url.rsplit("/", 1)[0] + "/" + s)
        fh.write(data); total += len(data)
print("downloaded %d segs (+init), %d bytes -> %s" % (len(segs), total, OUT))
