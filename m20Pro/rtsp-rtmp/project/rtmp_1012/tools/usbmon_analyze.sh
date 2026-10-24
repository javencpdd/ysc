#!/bin/bash
# usbmon_analyze.sh — 分析 usbmon 抓包与帧 PTS，定位"洞"在 USB 层的表现
cd /tmp
python3 - <<'PYEOF'
import subprocess, statistics

# --- 1. 解析 usbmon：每 URB 的时间戳与实际载荷长度 ---
urb = []
for ln in open('/tmp/usb2.log', errors='ignore'):
    f = ln.split()
    if len(f) < 6 or f[2] != 'C':
        continue
    try:
        ts = int(f[1])  # 微秒
        desc = f[4].split(':')  # '0:1:1768:0'
        length = int(desc[2])
    except (ValueError, IndexError):
        continue
    urb.append((ts, length))

if not urb:
    print('no URB parsed'); raise SystemExit

lens = [l for _, l in urb]
print('URB 总数: %d, 时长: %.1fs' % (len(urb), (urb[-1][0]-urb[0][0])/1e6))
print('载荷长度: min=%d p50=%d p95=%d max=%d 总字节=%.1fMB' % (
    min(lens), statistics.median(lens),
    sorted(lens)[int(len(lens)*0.95)], max(lens), sum(lens)/1e6))

# --- 2. 找"低载荷期"：连续 URB 载荷 < 阈值 ---
TH = 200
runs = []
start = None
for ts, l in urb:
    if l < TH:
        if start is None:
            start = ts
        last = ts
    else:
        if start is not None:
            runs.append((start, last))
            start = None
if start is not None:
    runs.append((start, last))

runs = [(a, b) for a, b in runs if (b - a) >= 50000]  # 只留 >=50ms 的
print('\n低载荷期(>=50ms, 载荷<%dB): %d 段' % (TH, len(runs)))
for a, b in runs[:15]:
    print('  %.0fms' % ((b - a) / 1000.0))
if runs:
    durs = [(b - a) / 1000.0 for a, b in runs]
    print('  合计 %.0fms, 均值 %.0fms, 最长 %.0fms' % (
        sum(durs), statistics.mean(durs), max(durs)))
PYEOF

echo ""
echo "=== 帧 PTS 洞（v1_probe.ts）==="
ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 /tmp/v1_probe.ts 2>/dev/null > /tmp/v1_probe.pts
python3 - <<'PYEOF'
pts = [float(l) for l in open('/tmp/v1_probe.pts') if l.strip() and l.strip() != 'N/A']
gaps = [b - a for a, b in zip(pts, pts[1:]) if b - a > 0]
if not gaps:
    print('no frames'); raise SystemExit
big = [g for g in gaps if g >= 0.100]
print('帧数=%d 时长=%.1fs 均帧率=%.1ffps' % (len(pts), pts[-1]-pts[0], (len(pts)-1)/(pts[-1]-pts[0])))
print('帧间隔>=100ms: %d 次, 均值 %.0fms, 最长 %.0fms' % (
    len(big), (sum(big)/len(big)*1000) if big else 0, max(gaps)*1000))
PYEOF
