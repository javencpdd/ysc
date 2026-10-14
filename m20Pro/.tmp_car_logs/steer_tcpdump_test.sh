#!/bin/bash
# Decisive test: tcpdump on UDP:30000 + single-shot zero axis + basic_server log check
source /opt/ros/foxy/setup.bash 2>/dev/null

echo '=== [1] tcpdump start (background, 12s) ==='
( printf "'\n" | sudo -S timeout 12 tcpdump -i lo -nn -A 'udp port 30000' > /tmp/udp30000.txt 2>&1 ) &
TP=$!
sleep 2

echo '=== [2] capture /STEER (background) ==='
timeout 9 ros2 topic echo /STEER > /tmp/cap_steer2.txt 2>&1 &
P1=$!

echo '=== [3] enable + lease + 2x single-shot ZERO axis ==='
curl -s --max-time 5 -X POST http://127.0.0.1:8080/api/v1/control/enable -H 'Content-Type: application/json' -d '{"confirmed": true, "enable": true}'
echo
curl -s --max-time 5 -X POST http://127.0.0.1:8080/api/v1/control/lease
echo
curl -s --max-time 5 -X POST http://127.0.0.1:8080/api/v1/control/axis -H 'Content-Type: application/json' -d '{"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0, "continuous": false}'
echo
sleep 1
curl -s --max-time 5 -X POST http://127.0.0.1:8080/api/v1/control/axis -H 'Content-Type: application/json' -d '{"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0, "continuous": false}'
echo
sleep 2
curl -s --max-time 5 -X POST http://127.0.0.1:8080/api/v1/control/enable -H 'Content-Type: application/json' -d '{"confirmed": true, "enable": false}'
echo

echo '=== [4] control status AFTER ==='
curl -s --max-time 5 http://127.0.0.1:8080/api/v1/control/status
echo

wait $P1 $TP 2>/dev/null
echo '=== [5] /STEER capture ==='
cat /tmp/cap_steer2.txt
echo '=== [6] UDP:30000 dump ==='
head -150 /tmp/udp30000.txt
echo '=== [7] Basic_server log tail ==='
tail -8 /var/opt/robot/log/2026_1015/Basic_server.2026_1015.log
echo '=== DONE ==='
