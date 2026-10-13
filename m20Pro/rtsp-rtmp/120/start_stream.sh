#!/bin/bash

cd /home/ysc/rtsp_stream
./start_server.sh &
./push_video.sh &
