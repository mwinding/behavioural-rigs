from picamera2 import Picamera2, Preview
import time
from libcamera import controls

experiment_duration = 7200
framerate = 1.0 #frames per second
experiment_name = ''

picam2 = Picamera2()
camera_config = picam2.create_preview_configuration()
picam2.configure(camera_config)
picam2.start()
picam2.set_controls({"AfMode": controls.AfModeEnum.Manual, "LensPosition": 10.0, "FrameRate": framerate})
picam2.start_and_record_video(f"{experiment_name}.mp4", duration = experiment_duration)