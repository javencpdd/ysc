#!/bin/bash
echo "=== video0 UVC controls (AE?) ==="
v4l2-ctl -d /dev/video0 -L 2>&1 | head -60
echo ""
echo "=== video0 formats ==="
v4l2-ctl -d /dev/video0 --list-formats-ext 2>&1 | head -30
