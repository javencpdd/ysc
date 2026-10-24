#!/bin/bash
# compare_streams.sh — 三路推流同条件帧间隔对比（只读，不中断任何服务）
# A 组：M20 video1(前) / M20 video2(后) / Lite3(参照系)，均从 M20 本机拉 HLS
# 指标：平均帧率、帧间隔抖动(p99)、>100ms 丢帧事件数、>150ms 严重卡顿数
OUT=/home/user/stream_compare
mkdir -p $OUT
DUR=22   # 录制时长（HLS 起播有缓冲，多录 2s）

pull() {  # $1=名称 $2=URL
    local name=$1 url=$2
    ffmpeg -v error -y -i "$url" -c copy -t $DUR -f mpegts "$OUT/$name.ts" 2>"$OUT/$name.pullerr"
    local rc=$?
    local sz=$(stat -c%s "$OUT/$name.ts" 2>/dev/null || echo 0)
    echo "[$name] ffmpeg rc=$rc size=${sz}B $( [ $sz -eq 0 ] && head -2 "$OUT/$name.pullerr" )"
}

echo "=== A 组：从 M20 本机拉三路 HLS（$DUR s）==="
date '+start %T'
pull v1_m20_front  "http://127.0.0.1:8888/video1/index.m3u8"
pull v2_m20_back   "http://127.0.0.1:8888/video2/index.m3u8"
pull lite3_ref     "http://192.168.2.1:8888/test/index.m3u8"
date '+end   %T'

echo ""
echo "=== 帧间隔分析 ==="
for f in "$OUT"/v1_m20_front.ts "$OUT"/v2_m20_back.ts "$OUT"/lite3_ref.ts; do
    n=$(basename "$f" .ts)
    ffprobe -v error -select_streams v:0 \
        -show_entries "packet=pts_time" -of csv=p=0 "$f" 2>/dev/null > "$OUT/$n.pts"
    python3 - "$n" "$OUT/$n.pts" <<'PYEOF'
import sys
name, path = sys.argv[1], sys.argv[2]
pts = []
with open(path) as fh:
    for line in fh:
        line = line.strip()
        if not line or line == 'N/A':
            continue
        try:
            pts.append(float(line))
        except ValueError:
            pass
if len(pts) < 10:
    print("%-14s 样本不足(%d) 拉流失败?" % (name, len(pts)))
    sys.exit(0)
gaps = [b - a for a, b in zip(pts, pts[1:]) if b - a > 0]
n = len(gaps)
avg = sum(gaps) / n
gaps_sorted = sorted(gaps)
p50 = gaps_sorted[int(n * 0.50)]
p95 = gaps_sorted[min(n - 1, int(n * 0.95))]
p99 = gaps_sorted[min(n - 1, int(n * 0.99))]
stall100 = sum(1 for g in gaps if g > 0.100)
stall150 = sum(1 for g in gaps if g > 0.150)
dur = pts[-1] - pts[0]
print("%-14s 时长%5.1fs 帧数%4d 均帧率%5.1ffps | p50=%5.1fms p95=%5.1fms p99=%6.1fms | >100ms丢帧%3d次 >150ms严重%3d次"
      % (name, dur, n + 1, (n + 1) / dur if dur > 0 else 0,
         p50 * 1000, p95 * 1000, p99 * 1000, stall100, stall150))
PYEOF
done

echo ""
echo "=== 分辨率/码率 ==="
for f in "$OUT"/v1_m20_front.ts "$OUT"/v2_m20_back.ts "$OUT"/lite3_ref.ts; do
    n=$(basename "$f" .ts)
    ffprobe -v error -select_streams v:0 -show_entries "stream=width,height,avg_frame_rate,bit_rate" -of csv=p=0 "$f" 2>/dev/null | sed "s/^/[$n] /"
done
echo ""
echo "saved to $OUT"
