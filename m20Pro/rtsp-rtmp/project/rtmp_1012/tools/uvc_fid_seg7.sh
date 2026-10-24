#!/bin/bash
# uvc_fid_seg.sh — 按 FID 分段统计：相机每个"帧"实际发了多少字节、用了多久
cd /tmp
python3 - <<'PYEOF'
import statistics

events = []
for ln in open('/tmp/usb7.log', errors='ignore'):
    if ' C ' not in ln or ' = ' not in ln:
        continue
    head, data = ln.split(' = ', 1)
    f = head.split()
    try:
        ts = int(f[1]); length = int(f[4].split(':')[2])
        raw = bytes.fromhex(''.join(data.split()))
    except (ValueError, IndexError):
        continue
    if len(raw) < 2:
        continue
    events.append((ts, raw[1] & 1, (raw[1] >> 1) & 1, length))

# 按 FID 切段（FID 变化 = 相机开始下一帧）
segs = []
cur = None
for ts, fid, eof, length in events:
    if cur is None or fid != cur['fid']:
        if cur:
            segs.append(cur)
        cur = {'fid': fid, 'start': ts, 'end': ts, 'bytes': 0, 'urbs': 0, 'eof': 0}
    cur['end'] = ts
    cur['bytes'] += length
    cur['urbs'] += 1
    cur['eof'] += eof
if cur:
    segs.append(cur)

print('FID 段数: %d' % len(segs))
if len(segs) < 3:
    raise SystemExit

durs = [(s['end'] - s['start']) / 1000.0 for s in segs]
bytess = [s['bytes'] for s in segs]
print('段时长(ms): p50=%.0f p95=%.0f max=%.0f' % (
    statistics.median(durs), sorted(durs)[int(len(durs)*0.95)], max(durs)))
print('段字节(B): p50=%d p95=%d max=%d 平均=%d' % (
    statistics.median(bytess), sorted(bytess)[int(len(bytess)*0.95)], max(bytess), statistics.mean(bytess)))
print('段时长>=100ms 的占比: %.1f%%' % (100.0*sum(1 for d in durs if d >= 100)/len(durs)))

# 大段明细
print('\n最长的 10 段（含字节数）:')
for s in sorted(segs, key=lambda x: x['end']-x['start'], reverse=True)[:10]:
    print('  %5.0fms  %6dB  %2d URB  eof=%d' % (
        (s['end']-s['start'])/1000.0, s['bytes'], s['urbs'], s['eof']))

# 段时长分布直方图
print('\n段时长分布:')
bins = [(0,40),(40,70),(70,100),(100,150),(150,250),(250,600),(600,10**9)]
for lo, hi in bins:
    n = sum(1 for d in durs if lo <= d < hi)
    print('  %4d-%4dms: %3d 段 (%4.1f%%)' % (lo, min(hi,9999), n, 100.0*n/len(durs)))

# 总吞吐 vs 交付帧率核算
span = (events[-1][0] - events[0][0]) / 1e6
total = sum(e[3] for e in events)
print('\n核算: 总 %.1fMB / %.1fs = %.0fKB/s; FID段 %d / %.1fs = %.1f 段/s' % (
    total/1e6, span, total/1024.0/span, len(segs), span, len(segs)/span))
PYEOF
