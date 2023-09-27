from picamera2 import Picamera2, Preview
import time
from libcamera import controls

experiment_duration = 7200

picam2 = Picamera2()
camera_config = picam2.create_preview_configuration()
picam2.configure(camera_config)
picam2.start()
picam2.set_controls({"AfMode": controls.AfModeEnum.Manual, "LensPosition": 10.0})
picam2.start_and_record_video("pc32_north_2hr_2023-09-26_rep7.mp4", duration = experiment_duration)