#!/usr/bin/python3
import time
from picamera2 import Picamera2
import os
import numpy as np

picam2 = Picamera2()
picam2.configure("still")
picam2.start()

experiment_name ='exp_test_zero_long-cable' # will create a folder with this name

duration = 180 # total time of timelapse, in seconds
interval = 60 # time between acquisitions, in seconds
num_captures = int(duration / interval) + 1

N = 96 # Total number of images acquired

# Create the output directory if it doesn't exist
os.makedirs(experiment_name, exist_ok=True)

# Record the initial time for reference
last_capture_time = time.time()

capture_times = []
for i in range(N):

    # acquire image
    r = picam2.capture_request()
    r.save("main", f"{experiment_name}/{experiment_name}_image{str(i).zfill(5)}.jpg")

    # Calculate the elapsed time from the start of the time-lapse
    elapsed_time = time.time() - start_time
    capture_times.append(elapsed_time)
    print(f"Captured image {i} of {N} at {elapsed_time:.2f}s")

    r.release()

    # Calculate the expected time for the next capture
    expected_next_capture_time = (i + 1) * interval

    # Calculate the time to sleep for the next capture
    sleep_duration = max(0, expected_next_capture_time - elapsed_time)
    
    time.sleep(sleep_duration)

picam2.stop()