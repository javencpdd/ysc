#!/bin/bash
echo "=== v4l2-ctl version ==="
v4l2-ctl --version 2>&1 | head -2
echo "=== /dev/video0 formats ==="
v4l2-ctl -d /dev/video0 --list-formats-ext 2>&1 | head -60
