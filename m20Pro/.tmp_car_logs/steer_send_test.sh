#!/bin/bash
# Zero-risk verification: does console -> basic_server -> /STEER DDS path actually emit frames?
# Uses single-shot (continuous:false) ZERO-speed axis frames. No watchdog, no estop, no motion.

source /opt/ros/foxy/setup.bash 2>/dev/null

echo '=== [0] warm up ros2 daemon ==='
timeout 20 ros2 topic list > /dev/null 2>&1
echo 'daemon warmed'

echo '=== [1] start background capture on /STEER and /HANDLE_STEER ==='
timeout 10 ros2 topic echo /STEER > /tmp/cap_steer.txt 2>&1 &
P1=$!
timeout 10 ros2 topic echo /HANDLE_STEER > /tmp/cap_hsteer.txt 2>&1 &
P2=$!
sleep 3

echo '=== [2] control status BEFORE ==='
curl -s --max-time 5 http://127.0.0.1:8080/api/v1/control/status
echo
echo '=== [3] enable control ==='
curl -s --max-time 5 -X POST http://127.0.0.1:8080/api/v1/control/enable -H 'Content-Type: application/json' -d '{"confirmed": true, "enable": true}'
echo
echo '=== [4] renew lease ==='
curl -s --max-time 5 -X POST http://127.0.0.1:8080/api/v1/control/lease
echo

echo '=== [5] single-shot ZERO axis x3 ==='
for i in 1 2 3; do
  echo "--- shot $i ---"
  curl -s --max-time 5 -X POST http://127.0.0.1:8080/api/v1/control/axis -H 'Content-Type: application/json' -d '{"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0, "continuous": false}'
  echo
  sleep 1
done

echo '=== [6] disable control ==='
curl -s --max-time 5 -X POST http://127.0.0.1:8080/api/v1/control/enable -H 'Content-Type: application/json' -d '{"confirmed": true, "enable": false}'
echo

wait $P1 $P2 2>/dev/null
echo '=== [7] /STEER capture ==='
cat /tmp/cap_steer.txt
echo '=== [8] /HANDLE_STEER capture ==='
cat /tmp/cap_hsteer.txt
echo '=== DONE ==='
