#!/bin/bash
# srs_probe.sh —— 从 SRS 拉流数真实帧数/间隔（判断推流端与 SRS 计数是否一致）
# 用法: srs_probe.sh <stream_name> [秒数] [rtmp|flv]
S="${1:-m20pro-f}"; DUR="${2:-10}"; MODE="${3:-rtmp}"
if [ "$MODE" = "flv" ]; then
  URL="http://172.31.68.227:8080/live/${S}.flv"
else
  URL="rtmp://172.31.68.227:1936/live/${S}"
fi
OUT="/tmp/srs_${S}.flv"
rm -f "$OUT"
echo "=== $S ($MODE) ${DUR}s ==="
echo "  URL: $URL"
timeout -s INT $((DUR+10)) ffmpeg -v error -rtmp_live live -i "$URL" -c copy -t "$DUR" -y "$OUT" 2>&1 | head -4
N=$(ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 "$OUT" 2>/dev/null | wc -l)
if [ "$N" -lt 2 ]; then echo "  无数据 (n=$N)"; exit 1; fi
awk -v n="$N" -v d="$DUR" 'BEGIN{printf "  帧数=%d  实际帧率=%.1f fps\n", n, n/d}'
echo -n "  时间跨度: "
ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 "$OUT" 2>/dev/null \
  | awk 'NR==1{f=$1} {l=$1} END{printf "%.2f 秒\n", l-f}'
echo "  帧间隔分布 top6 (ms:次数):"
ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 "$OUT" 2>/dev/null \
  | awk 'NR>1{printf "%.0f\n",($1-p)*1000} {p=$1}' | sort -n | uniq -c | sort -rn | head -6 \
  | awk '{printf "    %5s ms : %d 次\n", $2, $1}'
echo "  关键帧数(GOP):"
ffprobe -v error -select_streams v:0 -show_entries packet=pts_time,flags -of csv=p=0 "$OUT" 2>/dev/null \
  | grep -c K | sed 's/^/    /'
