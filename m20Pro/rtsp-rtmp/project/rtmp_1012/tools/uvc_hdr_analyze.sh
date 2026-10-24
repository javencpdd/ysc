#!/bin/bash
# uvc_hdr_analyze.sh — 解析 usbmon 数据前几字节的 UVC payload header，还原每帧的 FID/EOF 事件
cd /tmp
python3 - <<'PYEOF'
import statistics

# UVC 1.1 MJPEG payload header:
#   byte0 = bHeaderLength
#   byte1 = bmHeaderInfo: bit0 FID, bit1 EOF, bit2 PTS, bit6 ERR
events = []   # (ts_us, fid, eof, err, hdr_len, payload_len)
parse_err = 0
for ln in open('/tmp/usb2.log', errors='ignore'):
    if ' C ' not in ln or ' = ' not in ln:
        continue
    head, data = ln.split(' = ', 1)
    f = head.split()
    try:
        ts = int(f[1])
        desc = f[4].split(':')
        length = int(desc[2])
    except (ValueError, IndexError):
        parse_err += 1
        continue
    hb = ''.join(data.split())
    try:
        raw = bytes.fromhex(hb)
    except ValueError:
        parse_err += 1
        continue
    if len(raw) < 2:
        continue
    hl = raw[0]
    info = raw[1]
    events.append((ts, info & 1, (info >> 1) & 1, (info >> 6) & 1, hl, length))

print('解析事件: %d (解析失败 %d)' % (len(events), parse_err))
if not events:
    raise SystemExit

# header 长度分布
hl_dist = {}
for e in events:
    hl_dist[e[4]] = hl_dist.get(e[4], 0) + 1
print('header 长度分布: %s' % dict(sorted(hl_dist.items())[:8]))

err_cnt = sum(1 for e in events if e[3])
print('ERR 位置位次数: %d' % err_cnt)

# EOF 事件 = 帧完成
eof_ts = [e[0] for e in events if e[2]]
print('EOF 事件数(=完成帧数): %d' % len(eof_ts))
if len(eof_ts) > 2:
    gaps = [(b - a) / 1000.0 for a, b in zip(eof_ts, eof_ts[1:])]
    big = [g for g in gaps if g >= 100]
    print('EOF 间隔: 均 %.0fms p50=%.0fms p95=%.0fms max=%.0fms' % (
        statistics.mean(gaps), statistics.median(gaps),
        sorted(gaps)[int(len(gaps)*0.95)], max(gaps)))
    print('EOF 间隔 >=100ms: %d 次 (%.1f 次/s)' % (len(big), len(big) / ((eof_ts[-1]-eof_ts[0])/1e6)))

# FID 翻转事件 = 帧开始
fid_flips = 0
prev = None
flip_ts = []
for e in events:
    if prev is not None and e[1] != prev:
        fid_flips += 1
        flip_ts.append(e[0])
    prev = e[1]
print('FID 翻转次数(=开始新帧): %d, EOF/翻转 比 = %.2f' % (
    fid_flips, len(eof_ts) / fid_flips if fid_flips else 0))

# 洞期间（EOF 间隔>=100ms）的明细
if len(eof_ts) > 2:
    print('\n最长 8 个 EOF 洞及洞内 FID 行为:')
    pairs = list(zip(eof_ts, eof_ts[1:]))
    pairs.sort(key=lambda p: p[1]-p[0], reverse=True)
    for a, b in pairs[:8]:
        inside = [e for e in events if a < e[0] < b]
        fids = set(e[1] for e in inside)
        n_data = sum(1 for e in inside if e[5] > 100)
        bytes_in = sum(e[5] for e in inside)
        print('  %5.0fms 内: %d 个 URB, 总 %dB, FID 集合=%s, ERR=%d' % (
            (b-a)/1000.0, len(inside), bytes_in, sorted(fids),
            sum(1 for e in inside if e[3])))
PYEOF
