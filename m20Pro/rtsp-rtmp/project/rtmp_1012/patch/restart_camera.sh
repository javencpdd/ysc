#!/usr/bin/env bash
# ============================================================================
# restart_camera.sh —— 重启相机推流服务（保留已在运行的 mediamtx）
#
#   为什么不直接用官方的 restart.sh：
#     restart.sh 里是 `pkill -f push_video` + `pgrep -f gst-launch | kill -9`，
#     后者会无差别杀掉系统里所有 gst-launch（包括 rtmp_1012 的推流进程）。
#     这里改成精确匹配，只动相机侧。
#
#   ⚠ 本脚本必须"以文件形式执行"（bash restart_camera.sh），
#     不要把它内容直接贴到命令行里跑 —— 命令行里出现 push_video/v4l2 字样
#     会被上游其他脚本的 pkill -f 误伤。
# ============================================================================
set -u

CAM_SCRIPT=/opt/robot/scripts/board_resources/rtsp_service/push_video.sh
LOG=/tmp/camera_push.log

echo "--- 停止相机侧进程 ---"
pkill -f 'board_resources/rtsp_service/push_video' 2>/dev/null && echo "  已发送 TERM" || echo "  (无匹配进程)"
sleep 3

# 精确清理相机采集管道（只匹配 v4l2src 的，不碰其它 gst）
LEFT=$(pgrep -f 'gst-launch-1\.0 v4l2src' 2>/dev/null)
if [ -n "$LEFT" ]; then
    echo "  清理残留采集进程: $LEFT"
    kill -9 $LEFT 2>/dev/null
    sleep 2
fi

# 二次确认脚本是否退干净
LEFT2=$(pgrep -f 'board_resources/rtsp_service/push_video' 2>/dev/null)
[ -n "$LEFT2" ] && { echo "  强制清理残留脚本: $LEFT2"; kill -9 $LEFT2 2>/dev/null; sleep 1; }

echo "--- 启动相机推流 ---"
setsid nohup "$CAM_SCRIPT" > "$LOG" 2>&1 < /dev/null &
echo "  已拉起 push_video.sh，等待设备枚举与起流..."
sleep 20

echo "--- 校验 ---"
echo -n "  采集进程数: "; pgrep -cf 'gst-launch-1\.0 v4l2src' 2>/dev/null || echo 0
for p in video1 video2; do
    printf "  %-8s HLS=%s" "$p" "$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:8888/$p/index.m3u8)"
    # 取 SDP 判断编码
    codec=$(python3 - "$p" <<'PY' 2>/dev/null
import socket, sys, time
p = sys.argv[1]
try:
    s = socket.create_connection(('127.0.0.1', 8554), timeout=5)
    s.sendall(('DESCRIBE rtsp://127.0.0.1:8554/%s RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\n\r\n' % p).encode())
    time.sleep(1.5)
    d = s.recv(65535).decode('utf-8', 'replace')
    s.close()
    for line in d.splitlines():
        if line.startswith('a=rtpmap:'):
            print(line.split()[1].split('/')[0]); break
    else:
        print('n/a')
except Exception:
    print('err')
PY
)
    echo "  编码=$codec"
done
echo
echo "  最近日志:"; tail -5 "$LOG" 2>/dev/null | sed 's/^/    /'
