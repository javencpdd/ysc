# sudo gst-launch-1.0 v4l2src device=/dev/video0 ! image/jpeg, width=1280, height=720, framerate=30/1 ! jpegdec ! videoconvert ! mpph264enc ! rtspclientsink location=rtsp://127.0.0.1/live/test latency=10

sudo gst-launch-1.0 v4l2src device=/dev/video0 ! image/jpeg, width=1280, height=720, framerate=30/1 ! jpegdec ! videoconvert ! mpph264enc ! rtspclientsink location=rtsp://127.0.0.1:8554/test latency=10

