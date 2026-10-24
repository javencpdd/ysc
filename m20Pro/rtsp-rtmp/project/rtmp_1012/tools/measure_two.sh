#!/bin/bash
# measure_two.sh —— 单路/双路帧率与抖动测量
# 用法: measure_two.sh [video1|video2|both] [秒数]
# 只读：仅拉 RTSP 流做 ffprobe 分析，不触碰相机与推流进程
TARGET="${1:-both}"
DUR="${2:-20}"

stat_one() {
  local name="$1" dur="$2" f="/tmp/_m_${name}.mkv" d="/tmp/_d_${name}.txt"
  rm -f "$f" "$d"
  timeout -s INT $((dur+10)) ffmpeg -v error -rtsp_transport tcp \
    -i "rtsp://127.0.0.1:8554/${name}" -c copy -t "$dur" -y "$f" 2>/dev/null
  local n=$(ffprobe -v error -select_streams v:0 -show_entries packet=pts_time \
    -of csv=p=0 "$f" 2>/dev/null | wc -l)
  if [ "$n" -lt 5 ]; then echo "  $name: 采样失败 (n=$n)"; rm -f "$f" "$d"; return; fi
  ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 "$f" 2>/dev/null \
    | awk 'NR>1{printf "%.2f\n", ($1-p)*1000} {p=$1}' > "$d"
  local c=$(wc -l < "$d")
  sort -n "$d" -o "$d"
  awk -v N="$n" -v D="$dur" -v NM="$name" -v C="$c" '
    { a[NR]=$1; if ($1>150) ov150++; if ($1>500) ov500++; if ($1>1000) ov1000++ }
    END {
      i50=int(C*0.50)+1; if(i50<1)i50=1; if(i50>C)i50=C
      i95=int(C*0.95)+1; if(i95<1)i95=1; if(i95>C)i95=C
      i99=int(C*0.99)+1; if(i99<1)i99=1; if(i99>C)i99=C
      printf "  %-7s fps=%.1f  p50=%.0fms p95=%.0fms p99=%.0fms max=%.0fms  >150ms=%d >500ms=%d >1s=%d\n",
             NM, N/D, a[i50], a[i95], a[i99], a[C], ov150+0, ov500+0, ov1000+0
    }' "$d"
  rm -f "$f" "$d"
}

case "$TARGET" in
  video1|video2) stat_one "$TARGET" "$DUR" ;;
  both)          stat_one video1 "$DUR"; stat_one video2 "$DUR" ;;
  *) echo "用法: $0 [video1|video2|both] [秒数]"; exit 1 ;;
esac
